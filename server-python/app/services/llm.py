"""LLM inference client — calls the local llama-server via HTTP.

The shared core is `llama_sse_completion()`: an async generator that streams
events from llama-server (delta, model, usage, first_token). Higher-level
wrappers consume it differently:

  - `generate_completion()` — buffers all deltas and returns the assembled
    response (used by callers that don't need live UI streaming and aren't
    routed through job_manager). Most modern code passes `job=...` directly
    to the higher-level service (chub_importer, title_generator, etc.) so
    LLM events stream into the job — this stays as the simple fallback.
  - `services/llm_stream.py::stream_*` — parse the deltas character-by-character
    through a structured-output parser to emit semantic events for the UI.

All callers serialise through `_get_lock()`, so only one llama-server
inference runs at a time. (`services/job_manager.py` enforces the same
ordering at the job-manager level — both layers must agree, but the lock
here is what physically stops two HTTP requests from racing into the
single-slot llama-server process.)
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.services.llm_process import get_base_url
from app.services import llm_activity

log = logging.getLogger("pendrift.llm")

# ── Serialization queue ─────────────────────────────────
# Only one LLM call hits llama-server at a time. Lazy-init so module import
# works without a running event loop.
_queue: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _queue
    if _queue is None:
        _queue = asyncio.Lock()
    return _queue


# ── Body builder ────────────────────────────────────────
def _build_body(messages: list[dict], **kwargs) -> dict:
    """Build the request body, including only set sampling params + grammar."""
    body: dict = {"messages": messages}
    for k in ("temperature", "max_tokens", "top_p", "top_k", "min_p",
              "repeat_penalty", "presence_penalty", "frequency_penalty", "seed"):
        v = kwargs.get(k)
        if v is not None:
            body[k] = v
    if kwargs.get("grammar"):
        body["grammar"] = kwargs["grammar"]
    return body


def _extract_usage(data: dict, duration_ms: int) -> dict:
    usage = data.get("usage", {}) or {}
    return {
        "durationMs": duration_ms,
        "promptTokens": usage.get("prompt_tokens"),
        "completionTokens": usage.get("completion_tokens"),
        "totalTokens": usage.get("total_tokens"),
    }


# ── Shared SSE core ─────────────────────────────────────
async def llama_sse_completion(
    body: dict,
    *,
    activity_call=None,
    kind: str = "completion",
) -> AsyncIterator[dict]:
    """Stream raw events from llama-server's /v1/chat/completions SSE.

    Always uses streaming under the hood (so prompt-processing time and
    token rate are observable in real time). Yields normalized events:

      {"type": "first_token", "ms": int}
      {"type": "delta", "text": str}             # only when delta.content non-empty
      {"type": "model", "name": str}             # from chunk["model"]
      {"type": "usage", "data": dict}            # from chunk["usage"]

    Reasoning content (`delta.reasoning_content`) is counted but not yielded
    — `chat_template_kwargs.enable_thinking=False` should already suppress
    it, this is a defensive log path.

    No terminal "done" event — the caller knows the stream is over by
    StopAsyncIteration. Exceptions (httpx errors, CancelledError) propagate
    so the caller can decide how to surface them.

    Side effects:
      - Logs `POST` line with kind/messages/grammar/max_tokens.
      - Logs `SSE connected, waiting for first token…`.
      - Heartbeat log every 10s while waiting for first token.
      - Logs `first token after Xms`.
      - Periodic progress log (`streaming… N tokens, X tok/s`) every ~5s.
      - If `activity_call` provided, calls `llm_activity.set_request` once
        and `update_progress` on each delta.
    """
    body = {
        **body,
        "stream": True,
        "stream_options": {"include_usage": True},
        # Disable the model's built-in <think> block. Our grammars already
        # include a `thinking` field; if we let the model emit a <think>
        # tag llama-server routes those tokens to delta.reasoning_content
        # and bypasses the grammar entirely, giving us empty content.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    base = get_base_url()
    url = f"{base}/v1/chat/completions"

    n_msgs = len(body.get("messages") or [])
    prompt_chars = sum(len(m.get("content") or "") for m in (body.get("messages") or []))
    has_grammar = "grammar" in body
    max_tokens = body.get("max_tokens", "-")
    log.info(
        "[%s] POST /v1/chat/completions  messages=%d  prompt_chars=%d  grammar=%s  max_tokens=%s",
        kind, n_msgs, prompt_chars, has_grammar, max_tokens,
    )

    if activity_call is not None:
        llm_activity.set_request(activity_call, body)

    # Heartbeat while waiting for first token. llama-server stays silent
    # during prompt processing so without this the log looks dead.
    heartbeat_stop = asyncio.Event()

    async def _heartbeat():
        hb_start = time.monotonic()
        while not heartbeat_stop.is_set():
            try:
                await asyncio.wait_for(heartbeat_stop.wait(), timeout=10.0)
                return
            except asyncio.TimeoutError:
                log.info("[%s] still waiting… (%ds elapsed, llama-server likely prompt-processing)",
                         kind, int(time.monotonic() - hb_start))

    hb_task = asyncio.create_task(_heartbeat())

    start = time.monotonic()
    first_token_at: float | None = None
    token_count = 0
    reasoning_token_count = 0
    last_progress_log = 0.0
    bad_chunks = 0

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", url, json=body) as resp:
                resp.raise_for_status()
                log.info("[%s] SSE connected, waiting for first token…", kind)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        bad_chunks += 1
                        continue

                    if chunk.get("model"):
                        yield {"type": "model", "name": chunk["model"]}
                    if chunk.get("usage"):
                        yield {"type": "usage", "data": chunk["usage"]}

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning_piece = delta.get("reasoning_content")
                    piece = delta.get("content")

                    if reasoning_piece:
                        reasoning_token_count += 1

                    if (piece or reasoning_piece) and first_token_at is None:
                        first_token_at = time.time()
                        heartbeat_stop.set()
                        ms = int((time.monotonic() - start) * 1000)
                        log.info("[%s] first token after %dms", kind, ms)
                        yield {"type": "first_token", "ms": ms}

                    if not piece:
                        continue

                    token_count += 1
                    if activity_call is not None:
                        llm_activity.update_progress(
                            activity_call,
                            tokens=token_count,
                            first_token_at=first_token_at,
                        )

                    now = time.monotonic()
                    if now - last_progress_log > 5.0:
                        elapsed_gen = time.time() - first_token_at if first_token_at else 0
                        rate = token_count / elapsed_gen if elapsed_gen > 0.1 else 0
                        log.info("[%s] streaming… %d content tokens (%.1f tok/s)",
                                 kind, token_count, rate)
                        last_progress_log = now

                    yield {"type": "delta", "text": piece}
    finally:
        heartbeat_stop.set()
        try:
            await hb_task
        except asyncio.CancelledError:
            pass
        if bad_chunks:
            log.warning("[%s] dropped %d malformed SSE chunks", kind, bad_chunks)
        if reasoning_token_count:
            log.info("[%s] saw %d reasoning_content tokens (likely model defied enable_thinking=False)",
                     kind, reasoning_token_count)


# ── Buffered consumers (no live streaming to UI) ────────
async def _buffered_completion(
    body: dict,
    activity_call,
    kind: str,
) -> tuple[dict, int]:
    """Consume `llama_sse_completion` into a buffered response shaped like
    the non-streaming OpenAI completion. Returns (assembled, duration_ms)."""
    content_pieces: list[str] = []
    usage: dict = {}
    model_name = ""
    start = time.monotonic()

    async for ev in llama_sse_completion(body, activity_call=activity_call, kind=kind):
        if ev["type"] == "delta":
            content_pieces.append(ev["text"])
        elif ev["type"] == "model":
            model_name = ev["name"]
        elif ev["type"] == "usage":
            usage = ev["data"]

    duration_ms = int((time.monotonic() - start) * 1000)
    log.info("[%s] done  content_tokens~=%d  duration=%dms  usage=%s",
             kind, len(content_pieces), duration_ms, usage or "-")

    assembled = {
        "choices": [{"message": {"content": "".join(content_pieces)}}],
        "model": model_name,
        "usage": usage,
    }
    return assembled, duration_ms


async def generate_completion(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    min_p: float | None = None,
    repeat_penalty: float | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    seed: int | None = None,
    grammar: str | None = None,
    kind: str = "completion",
    session_id: str | None = None,
) -> dict:
    """Generic grammar-constrained completion for utility calls (title gen,
    chub import, meta-analysis, character consolidation).

    Callers `json.loads(result["raw"])` and pick their own fields.
    Returns: {raw, stats, modelName}.
    """
    call = llm_activity.register(kind, session_id)
    llm_activity.attach_task(call, asyncio.current_task())
    try:
        async with _get_lock():
            llm_activity.mark_running(call)
            body = _build_body(
                messages,
                temperature=temperature, max_tokens=max_tokens,
                top_p=top_p, top_k=top_k, min_p=min_p,
                repeat_penalty=repeat_penalty,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                seed=seed,
                grammar=grammar,
            )
            data, duration_ms = await _buffered_completion(body, call, kind)

        raw_content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        stats = _extract_usage(data, duration_ms)
        model = data.get("model", "")
        llm_activity.mark_done(call, stats=stats, model=model, raw_response=raw_content)
        return {"raw": raw_content, "stats": stats, "modelName": model}
    except asyncio.CancelledError:
        llm_activity.mark_done(call, error="cancelled")
        raise
    except Exception as e:
        llm_activity.mark_done(call, error=str(e))
        raise
