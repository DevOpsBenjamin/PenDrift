"""LLM inference client — calls the local llama-server via HTTP."""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.services.llm_process import get_base_url

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


async def _raw_completion(body: dict) -> tuple[dict, int]:
    """Send request to llama-server, return (response_json, duration_ms)."""
    base = get_base_url()
    url = f"{base}/v1/chat/completions"
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
    duration_ms = int((time.monotonic() - start) * 1000)
    return resp.json(), duration_ms


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

    async with _get_lock():
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
        data, duration_ms = await _raw_completion(body)

    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    parsed = json.loads(raw)

    return {
        "thinking": parsed.get("thinking", ""),
        "type": parsed.get("type", "narrative"),
        "narrative": parsed.get("narrative", ""),
        "suggestions": parsed.get("suggestions", []),
        "stats": _extract_usage(data, duration_ms),
        "modelName": data.get("model", ""),
        "raw": raw,
    }


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
    think_block_start: str = "<think>",
    think_block_end: str = "</think>",
) -> dict:
    """Generic completion for meta, title gen, format fixer, import, etc.

    Returns {narrative, thinking, raw, stats, modelName}.
    """
    from app.utils.think_parser import strip_think_blocks

    async with _get_lock():
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
        data, duration_ms = await _raw_completion(body)

    message = (data.get("choices") or [{}])[0].get("message", {})
    raw_content = message.get("content", "")

    if message.get("reasoning_content"):
        narrative = raw_content.strip()
        thinking = message["reasoning_content"]
    else:
        narrative, thinking = strip_think_blocks(raw_content, think_block_start, think_block_end)

    return {
        "narrative": narrative,
        "thinking": thinking,
        "raw": raw_content,
        "stats": _extract_usage(data, duration_ms),
        "modelName": data.get("model", ""),
    }


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
