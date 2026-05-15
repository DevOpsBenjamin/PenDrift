"""LLM inference façade — runner + provider façade.

Three layers, top-down:

1. **`run_llm_stream(messages, *, settings, kind, ...)`** — high-level event
   stream with all the boilerplate factored out. Handles provider
   selection, llama-server auto-start (local only), llm_activity
   register/mark_done, the global serialisation lock, SSE event
   consumption, and cancel/error mark-down. Yields `started`, then the
   raw `sse_completion` events (`delta`, `model`, `usage`, `first_token`),
   then `llm_done` with stats + raw text. Use this for streaming flows
   (narrative, query) that need live events.

2. **`run_llm_buffered(messages, *, settings, kind, job=None, ...)`** —
   convenience wrapper that consumes `run_llm_stream` into a single
   buffered result. Optional `job` parameter forwards every event so the
   toast bar / Activity view see live progress. Returns
   `{"raw": str, "stats": dict, "modelName": str}`. Used by every flow
   that only needs the final text (chub-import, meta, title, consolidate).

3. **`sse_completion(body, ...)`** — the lowest-level primitive. Pure
   provider façade: yields raw events from whichever provider is
   configured (llama-server, openai-compat, xai, ...). No lock, no
   activity, no model-load. Reserved for callers that need fine-grained
   control. Most code should use the runners above.

Provider selection lives in `services/providers/`. The runners read
`settings.provider` (default `"llama-server"`) + `settings.providerConfig`
to instantiate the right backend.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from app.services import llm_activity, llm_process, xai_budget
from app.services.providers import get_provider

log = logging.getLogger("pendrift.llm")


# ── Body builder ─────────────────────────────────────────
def _build_body(messages: list[dict], **kwargs) -> dict:
    """Build an OpenAI-compatible chat completion body. Includes only the
    sampling params that were explicitly set (None → field omitted)."""
    body: dict = {"messages": messages}
    for k in ("temperature", "max_tokens", "top_p", "top_k", "min_p",
              "repeat_penalty", "presence_penalty", "frequency_penalty", "seed"):
        v = kwargs.get(k)
        if v is not None:
            body[k] = v
    if kwargs.get("grammar"):
        body["grammar"] = kwargs["grammar"]
    return body


def _extract_usage(usage: dict, duration_ms: int) -> dict:
    return {
        "durationMs": duration_ms,
        "promptTokens": usage.get("prompt_tokens"),
        "completionTokens": usage.get("completion_tokens"),
        "totalTokens": usage.get("total_tokens"),
        # xAI-only: per-request cost in ticks (10B ticks = $1). None for other providers.
        "costInUsdTicks": usage.get("cost_in_usd_ticks"),
    }


def _provider_from_settings(settings: dict | None) -> tuple[str, dict]:
    s = settings or {}
    name = s.get("provider", "llama-server")
    config = s.get("providerConfig", {}).get(name, {})
    return name, config


def _merge_reasoning_into_json(content: str, reasoning: str) -> tuple[str, bool]:
    """Inject `reasoning_content` into the JSON content's `thinking` field.

    Grok / o-series provide two distinct CoT signals: a native streamed
    `reasoning_content` (the model's deep deliberation) AND a JSON `thinking`
    field that the narrative prompt asks for (focused setup notes for the
    chunk). When both are present they describe different work — the streamed
    one is the open-ended reasoning, the JSON one is the planned chunk
    scaffold. Keep both: streamed first, JSON next, separated by a markdown
    rule so the ThinkingPanel renders both as labeled sections.

    Returns (possibly-modified content, True if any injection happened)."""
    if not reasoning or not content.strip().startswith("{"):
        return content, False
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content, False

    existing = (parsed.get("thinking") or "").strip()
    if existing:
        parsed["thinking"] = (
            f"### Native reasoning (streamed)\n\n{reasoning.strip()}\n\n"
            f"---\n\n### Setup notes (planned)\n\n{existing}"
        )
    else:
        parsed = {"thinking": reasoning, **parsed}
    return json.dumps(parsed, ensure_ascii=False, indent=2), True


async def _ensure_provider_ready(
    settings: dict | None,
    *,
    on_event=None,
) -> None:
    """Auto-start llama-server if the preset targets it and it's not up.
    No-op for external providers (xai, openai, ...).

    If `on_event` is provided, emits `{"type": "model_loading", "modelPath"}`
    before starting and `{"type": "model_loaded"}` after — the SSE consumer
    sees the loading state instead of a silent multi-second freeze."""
    name, _ = _provider_from_settings(settings)
    if name != "llama-server":
        return
    if llm_process.is_running():
        return
    if on_event is not None:
        on_event({"type": "model_loading", "modelPath": (settings or {}).get("modelPath")})
    try:
        await llm_process.ensure_loaded(settings or {})
    except (RuntimeError, TimeoutError) as e:
        raise RuntimeError(f"Could not start llama-server: {e}") from e
    if on_event is not None:
        on_event({"type": "model_loaded"})


# ── Provider-agnostic SSE primitive (low-level) ──────────
async def sse_completion(
    body: dict,
    *,
    provider_name: str = "llama-server",
    provider_kwargs: dict | None = None,
    activity_call=None,
    kind: str = "completion",
) -> AsyncIterator[dict]:
    """Yield raw events from the configured provider. Caller owns lock,
    activity register, and model-load.

    Most callers should use `run_llm_stream` / `run_llm_buffered` instead —
    those wrap this with all the boilerplate."""
    provider = get_provider(provider_name, **(provider_kwargs or {}))
    async for event in provider.sse_completion(body, activity_call=activity_call, kind=kind):
        yield event


# ── High-level runners ───────────────────────────────────
async def run_llm_stream(
    messages: list[dict],
    *,
    settings: dict | None = None,
    kind: str = "completion",
    session_id: str | None = None,
    **sampling,
) -> AsyncIterator[dict]:
    """End-to-end LLM call as an event stream.

    Yields, in order:
      - (optional) {"type": "model_loading", "modelPath": str}
      - (optional) {"type": "model_loaded"}
      - {"type": "started", "callId": str}
      - all events from `sse_completion` (delta, model, usage, first_token)
      - {"type": "llm_done", "stats": dict, "modelName": str, "raw": str}

    The model_loading/model_loaded pair only appears when the local
    llama-server provider is configured and the daemon needed to be
    auto-started — gives the UI something to show during a multi-second
    cold start.

    Raises CancelledError / Exception unchanged after marking the activity
    call cancelled / errored. Callers can wrap to handle "save partial on
    cancel" flows.
    """
    provider_name, provider_config = _provider_from_settings(settings)

    # Pre-flight events (model load) happen BEFORE the inference lock so
    # the user sees "model loading" rather than a silent freeze.
    pre_events: list[dict] = []
    await _ensure_provider_ready(settings, on_event=pre_events.append)
    for pev in pre_events:
        yield pev

    body = _build_body(messages, **sampling)
    call = llm_activity.register(kind, session_id)
    llm_activity.attach_task(call, asyncio.current_task())

    full: list[str] = []
    thinking_pieces: list[str] = []
    usage: dict = {}
    model_name = ""
    start = time.monotonic()

    try:
        # No local lock here: every entry point is wrapped in a job by
        # services/job_manager.py, which already serialises across all
        # kinds. (For external providers like xAI / OpenAI the concept of
        # a serialisation lock is a non-sequitur anyway — they handle
        # concurrency on their side.)
        llm_activity.mark_running(call)
        yield {"type": "started", "callId": call.id}

        async for ev in sse_completion(
            body,
            provider_name=provider_name,
            provider_kwargs=provider_config,
            activity_call=call,
            kind=kind,
        ):
            if ev["type"] == "delta":
                full.append(ev["text"])
            elif ev["type"] == "thinking_delta":
                thinking_pieces.append(ev["text"])
            elif ev["type"] == "model":
                model_name = ev["name"]
            elif ev["type"] == "usage":
                usage = ev["data"]
            yield ev

        duration_ms = int((time.monotonic() - start) * 1000)
        raw = "".join(full)
        reasoning = "".join(thinking_pieces)
        # Merge CoT (reasoning_content) into the JSON's `thinking` field BEFORE
        # mark_done so the activity dump captures the full picture.
        raw, injected = _merge_reasoning_into_json(raw, reasoning)
        if injected:
            log.info("[%s] injected reasoning_content into JSON 'thinking' field", kind)
        stats = _extract_usage(usage, duration_ms)
        llm_activity.mark_done(call, stats=stats, model=model_name, raw_response=raw)
        if provider_name == "xai":
            xai_budget.apply_local_cost(stats.get("costInUsdTicks"))
        yield {"type": "llm_done", "stats": stats, "modelName": model_name, "raw": raw}
    except asyncio.CancelledError:
        partial, _ = _merge_reasoning_into_json("".join(full), "".join(thinking_pieces))
        llm_activity.mark_done(call, error="cancelled", raw_response=partial or None)
        raise
    except Exception as e:
        partial, _ = _merge_reasoning_into_json("".join(full), "".join(thinking_pieces))
        llm_activity.mark_done(call, error=str(e), raw_response=partial or None)
        raise


async def run_llm_buffered(
    messages: list[dict],
    *,
    settings: dict | None = None,
    kind: str = "completion",
    session_id: str | None = None,
    job: Any = None,
    **sampling,
) -> dict:
    """Buffered LLM call: consume `run_llm_stream` into a single result.
    If `job` is provided, every stream event is forwarded so the toast bar
    sees live progress (token-by-token).

    Returns: {"raw": str, "stats": dict, "modelName": str}.

    The `raw` already has its `thinking` field merged from `reasoning_content`
    when applicable — that injection happens inside `run_llm_stream` before
    activity mark_done, so the activity dump and this return value match."""
    raw = ""
    stats: dict = {}
    model_name = ""

    async for ev in run_llm_stream(
        messages, settings=settings, kind=kind, session_id=session_id, **sampling
    ):
        if ev["type"] == "model":
            model_name = ev["name"]
        elif ev["type"] == "llm_done":
            raw = ev["raw"]
            stats = ev["stats"]
        if job is not None:
            job.emit(ev)

    return {"raw": raw, "stats": stats, "modelName": model_name}


# ── Backward-compat alias ────────────────────────────────
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
    settings: dict | None = None,
) -> dict:
    """Thin alias around `run_llm_buffered` for legacy callers. New code
    should call `run_llm_buffered` directly — it's the same shape."""
    return await run_llm_buffered(
        messages,
        settings=settings,
        kind=kind,
        session_id=session_id,
        temperature=temperature, max_tokens=max_tokens,
        top_p=top_p, top_k=top_k, min_p=min_p,
        repeat_penalty=repeat_penalty,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        seed=seed,
        grammar=grammar,
    )
