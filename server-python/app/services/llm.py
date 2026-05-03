"""LLM inference client — provider-agnostic façade.

The shared core is `sse_completion()`: an async generator that yields
normalized events (`delta`, `model`, `usage`, `first_token`) from the
configured LLM provider. Each provider (currently llama-server, with an
OpenAI-compatible stub in place for future) implements the underlying HTTP
+ SSE handling — this file just delegates and adds the buffered-completion
convenience wrapper.

Higher-level wrappers in this file:

  - `generate_completion()` — buffers all deltas and returns the assembled
    response (used by callers that don't need live UI streaming and aren't
    routed through job_manager). Most modern code passes `job=...` directly
    to the higher-level service (chub_importer, title_generator, etc.) so
    LLM events stream into the job — this stays as the simple fallback.
  - `services/llm_stream.py::stream_*` — parse the deltas character-by-character
    through a structured-output parser to emit semantic events for the UI.

All callers serialise through `_get_lock()`, so only one inference runs at
a time. (`services/job_manager.py` enforces the same ordering at the
job-manager level — both layers must agree, but the lock here is what
physically stops two HTTP requests from racing into a single-slot backend
like llama-server.)
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

from app.services import llm_activity
from app.services.providers import get_provider

log = logging.getLogger("pendrift.llm")

# Provider Selection
# Provider is now dynamically selected based on the preset settings.

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
    return body


def _extract_usage(data: dict, duration_ms: int) -> dict:
    usage = data.get("usage", {}) or {}
    return {
        "durationMs": duration_ms,
        "promptTokens": usage.get("prompt_tokens"),
        "completionTokens": usage.get("completion_tokens"),
        "totalTokens": usage.get("total_tokens"),
    }


# ── Provider-agnostic SSE entry point ────────────────────
async def sse_completion(
    body: dict,
    *,
    provider_name: str = "llama-server",
    provider_kwargs: dict | None = None,
    activity_call=None,
    kind: str = "completion",
) -> AsyncIterator[dict]:
    """Yield normalized events from the configured LLM provider.

    Event shape (all providers translate their native format into this):
      {"type": "first_token", "ms": int}
      {"type": "delta", "text": str}             # only when content non-empty
      {"type": "model", "name": str}
      {"type": "usage", "data": dict}

    No terminal "done" event — caller sees StopAsyncIteration. Exceptions
    propagate (httpx errors, CancelledError, etc.) so the caller decides
    how to surface them.
    """
    kwargs = provider_kwargs or {}
    provider = get_provider(provider_name, **kwargs)
    # NOTE: callers (stream_narrative, _llm_template_call, run_meta_analysis,
    # generate_chapter_title, consolidate, generate_completion) already hold
    # `_get_lock()` around their entire flow. `asyncio.Lock` is NOT reentrant —
    # acquiring it here would deadlock the same task on every LLM call.
    async for event in provider.sse_completion(body, activity_call=activity_call, kind=kind):
        yield event


# ── Buffered consumers (no live streaming to UI) ────────
async def _buffered_completion(
    body: dict,
    activity_call,
    kind: str,
    provider_name: str,
    provider_kwargs: dict,
) -> tuple[dict, int]:
    """Consume `sse_completion` into a buffered response shaped like the
    non-streaming OpenAI completion. Returns (assembled, duration_ms)."""
    content_pieces: list[str] = []
    thinking_pieces: list[str] = []
    usage: dict = {}
    model_name = ""
    start = time.monotonic()

    async for ev in sse_completion(body, provider_name=provider_name, provider_kwargs=provider_kwargs, activity_call=activity_call, kind=kind):
        if ev["type"] == "delta":
            content_pieces.append(ev["text"])
        elif ev["type"] == "thinking_delta":
            thinking_pieces.append(ev["text"])
        elif ev["type"] == "model":
            model_name = ev["name"]
        elif ev["type"] == "usage":
            usage = ev["data"]

    duration_ms = int((time.monotonic() - start) * 1000)
    log.info("[%s] done  content_tokens~=%d  duration=%dms  usage=%s",
             kind, len(content_pieces), duration_ms, usage or "-")

    assembled = {
        "choices": [{"message": {
            "content": "".join(content_pieces),
            "reasoning_content": "".join(thinking_pieces)
        }}],
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
    kind: str = "completion",
    session_id: str | None = None,
    settings: dict | None = None,
) -> dict:
    """Generic structured completion for utility calls (title gen,
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
            )
            provider_name = (settings or {}).get("provider", "llama-server")
            provider_config = (settings or {}).get("providerConfig", {}).get(provider_name, {})
            # The outer `async with _get_lock()` above already serialises this
            # call. Don't re-acquire (asyncio.Lock is non-reentrant — would
            # deadlock the same task).
            data, duration_ms = await _buffered_completion(body, call, kind, provider_name, provider_config)

        msg = (data.get("choices") or [{}])[0].get("message", {})
        raw_content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")
        
        # If we have external reasoning but the JSON is missing the 'thinking' field, inject it
        if reasoning and raw_content.strip().startswith("{"):
            try:
                parsed = json.loads(raw_content)
                if "thinking" not in parsed or not parsed["thinking"]:
                    # Create a new dict with 'thinking' as the FIRST key
                    new_obj = {"thinking": reasoning}
                    new_obj.update(parsed)
                    raw_content = json.dumps(new_obj, ensure_ascii=False, indent=2)
                    log.info("[%s] Injected reasoning_content into JSON 'thinking' field", kind)
            except Exception:
                pass # Not a valid JSON or other error, leave it as is

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
