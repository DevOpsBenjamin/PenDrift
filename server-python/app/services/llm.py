"""LLM inference client — calls the local llama-server via HTTP."""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.services.llm_process import get_base_url
from app.services import llm_activity

log = logging.getLogger("pendrift.llm")

# Serialization queue — only one LLM call at a time
_queue: asyncio.Lock | None = None


def _get_lock():
    global _queue
    if _queue is None:
        _queue = asyncio.Lock()
    return _queue


def _build_body(messages: list[dict], **kwargs) -> dict:
    """Build the request body, only including set params."""
    body: dict = {"messages": messages, "stream": False}
    for k in ("temperature", "max_tokens", "top_p", "top_k", "min_p",
              "repeat_penalty", "presence_penalty", "frequency_penalty", "seed"):
        v = kwargs.get(k)
        if v is not None:
            body[k] = v
    if kwargs.get("grammar"):
        body["grammar"] = kwargs["grammar"]
    return body


async def _raw_completion(body: dict, activity_call=None) -> tuple[dict, int]:
    """Stream from llama-server, assemble the full response, update live activity.

    We always use stream=true so that `llm_activity` can reflect progress in
    real time (tokens generated, tok/s) without having to poll llama-server's
    /slots endpoint (which spams its log). The assembled response is returned
    in the same shape as the non-streaming completion so callers are unchanged.
    """
    body = {
        **body,
        "stream": True,
        "stream_options": {"include_usage": True},
        # Disable the model's built-in reasoning/<think> block. Our grammars
        # already provide a `thinking` field, and when thinking mode is on
        # llama-server routes tokens to `delta.reasoning_content` instead of
        # `delta.content` — bypassing grammar and giving us empty content.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    base = get_base_url()
    url = f"{base}/v1/chat/completions"

    kind = activity_call.kind if activity_call else "completion"
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

    # Heartbeat while waiting for first token (llama-server stays silent during prompt processing)
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

    content_pieces: list[str] = []
    reasoning_pieces: list[str] = []
    usage: dict = {}
    model_name = ""
    first_token_at: float | None = None
    token_count = 0
    reasoning_token_count = 0
    chunk_count = 0
    bad_chunks = 0
    last_progress_log = 0.0

    start = time.monotonic()
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
                chunk_count += 1

                if chunk.get("model"):
                    model_name = chunk["model"]
                if chunk.get("usage"):
                    usage = chunk["usage"]

                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    reasoning_piece = delta.get("reasoning_content")
                    piece = delta.get("content")

                    if reasoning_piece:
                        reasoning_pieces.append(reasoning_piece)
                        reasoning_token_count += 1

                    if piece or reasoning_piece:
                        if first_token_at is None:
                            first_token_at = time.time()
                            heartbeat_stop.set()
                            log.info("[%s] first token after %dms", kind, int((time.monotonic() - start) * 1000))

                    if piece:
                        content_pieces.append(piece)
                        token_count += 1
                        if activity_call is not None:
                            llm_activity.update_progress(
                                activity_call,
                                tokens=token_count,
                                first_token_at=first_token_at,
                            )
                        # Periodic progress log (every ~5s)
                        now = time.monotonic()
                        if now - last_progress_log > 5.0:
                            elapsed_gen = time.time() - first_token_at if first_token_at else 0
                            rate = token_count / elapsed_gen if elapsed_gen > 0.1 else 0
                            log.info("[%s] streaming… %d content tokens (%.1f tok/s)", kind, token_count, rate)
                            last_progress_log = now

    heartbeat_stop.set()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass
    duration_ms = int((time.monotonic() - start) * 1000)
    log.info(
        "[%s] done  content_tokens=%d  reasoning_tokens=%d  chunks=%d  bad_chunks=%d  duration=%dms  usage=%s",
        kind, token_count, reasoning_token_count, chunk_count, bad_chunks, duration_ms, usage or "-",
    )
    assembled = {
        "choices": [{"message": {"content": "".join(content_pieces)}}],
        "model": model_name,
        "usage": usage,
    }
    return assembled, duration_ms


def _extract_usage(data: dict, duration_ms: int) -> dict:
    usage = data.get("usage", {})
    return {
        "durationMs": duration_ms,
        "promptTokens": usage.get("prompt_tokens"),
        "completionTokens": usage.get("completion_tokens"),
        "totalTokens": usage.get("total_tokens"),
    }


# ── Narrative generation (grammar-structured) ───────────

async def generate_narrative(
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
    session_id: str | None = None,
) -> dict:
    """Grammar-constrained narrative generation.

    Returns:
        {
            "thinking": str,
            "type": "narrative" | "suggestion",
            "narrative": str,
            "suggestions": list[str],
            "stats": dict,
            "modelName": str,
        }
    """
    from app.utils.grammars import NARRATIVE_GRAMMAR

    call = llm_activity.register("narrative", session_id)
    llm_activity.attach_task(call, asyncio.current_task())
    try:
        async with _get_lock():
            llm_activity.mark_running(call)
            body = _build_body(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                repeat_penalty=repeat_penalty,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                seed=seed,
                grammar=NARRATIVE_GRAMMAR,
            )
            data, duration_ms = await _raw_completion(body, activity_call=call)

        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        stats = _extract_usage(data, duration_ms)
        model = data.get("model", "")
        llm_activity.mark_done(call, stats=stats, model=model, raw_response=raw)
        parsed = json.loads(raw)

        return {
            "thinking": parsed.get("thinking", ""),
            "type": parsed.get("type", "narrative"),
            "narrative": parsed.get("narrative", ""),
            "suggestions": parsed.get("suggestions", []),
            "stats": stats,
            "modelName": model,
            "raw": raw,
        }
    except asyncio.CancelledError:
        llm_activity.mark_done(call, error="cancelled")
        raise
    except Exception as e:
        llm_activity.mark_done(call, error=str(e))
        raise


# ── Generic completion (with optional grammar) ──────────

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
    chub import, consolidate). The grammar is expected to produce JSON with a
    leading `thinking` field; callers json.loads(result["raw"]) and pick their
    own fields.

    Returns {raw, stats, modelName}.
    """
    call = llm_activity.register(kind, session_id)
    llm_activity.attach_task(call, asyncio.current_task())
    try:
        async with _get_lock():
            llm_activity.mark_running(call)
            body = _build_body(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                repeat_penalty=repeat_penalty,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                seed=seed,
                grammar=grammar,
            )
            data, duration_ms = await _raw_completion(body, activity_call=call)

        raw_content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        stats = _extract_usage(data, duration_ms)
        model = data.get("model", "")
        llm_activity.mark_done(call, stats=stats, model=model, raw_response=raw_content)

        return {
            "raw": raw_content,
            "stats": stats,
            "modelName": model,
        }
    except asyncio.CancelledError:
        llm_activity.mark_done(call, error="cancelled")
        raise
    except Exception as e:
        llm_activity.mark_done(call, error=str(e))
        raise


# ── Streaming (for future SSE) ──────────────────────────

async def generate_completion_stream(
    messages: list[dict],
    **kwargs,
) -> AsyncIterator[str]:
    """SSE streaming completion. Yields text chunks."""
    async with _get_lock():
        base = get_base_url()
        url = f"{base}/v1/chat/completions"

        body = _build_body(messages, **kwargs)
        body["stream"] = True

        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", url, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
