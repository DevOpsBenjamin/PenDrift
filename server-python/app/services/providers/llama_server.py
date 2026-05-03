"""llama-server provider — talks to the local llama.cpp server over its
OpenAI-compatible /v1/chat/completions endpoint.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.services import llm_activity
from app.services.llm_process import get_base_url
from app.services.providers.base import ProgressLogger, start_heartbeat
from app.utils.structured_outputs import STRUCTURED_OUTPUTS

log = logging.getLogger("pendrift.providers.llama_server")


class LlamaServerProvider:
    """Stream raw events from llama-server's OpenAI-compatible chat endpoint."""

    name = "llama-server"

    def __init__(self, *, timeout_s: float = 600.0):
        self._timeout = timeout_s

    async def sse_completion(
        self,
        body: dict,
        *,
        activity_call=None,
        kind: str = "completion",
    ) -> AsyncIterator[dict]:
        body = {
            **body,
            "stream": True,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
        }

        # Inject grammar if a known kind is provided and not already present
        if kind in STRUCTURED_OUTPUTS and "grammar" not in body:
            body["grammar"] = STRUCTURED_OUTPUTS[kind]["gbnf"]
        url = f"{get_base_url()}/v1/chat/completions"

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
            log.info("[%s] Request payload dumped to data/llm-requests/%s", kind, activity_call.request_file)

        heartbeat_stop, hb_task = start_heartbeat(kind)
        progress = ProgressLogger(kind)

        start = time.monotonic()
        first_token_at: float | None = None
        reasoning_token_count = 0
        bad_chunks = 0

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
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
                            progress.first_token(ms)
                            yield {"type": "first_token", "ms": ms}

                        if not piece:
                            continue

                        progress.tick()
                        if activity_call is not None:
                            llm_activity.update_progress(
                                activity_call,
                                tokens=progress.token_count,
                                first_token_at=first_token_at,
                            )

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
                log.info(
                    "[%s] saw %d reasoning_content tokens (model defied enable_thinking=False)",
                    kind, reasoning_token_count,
                )

    def get_default_prompt(self, kind: str) -> str:
        from app.services.prompts_registry import get_prompt
        return get_prompt(kind, "llama-server") or "You are a helpful assistant."
