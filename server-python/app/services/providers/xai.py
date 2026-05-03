"""xAI provider — talks to the xAI chat completions API (grok-beta).

Supports streaming responses and maps xAI SSE events to PenDrift's
standard event format. GBNF grammar is not supported natively by xAI
and will be dropped with a warning if present.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator

import httpx

from app.services import llm_activity
from app.services.providers.base import ProgressLogger, start_heartbeat
from app.utils.structured_outputs import STRUCTURED_OUTPUTS

log = logging.getLogger("pendrift.providers.xai")


class XAIProvider:
    """Stream events from xAI's chat endpoint."""

    name = "xai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-beta",
        timeout_s: float = 600.0,
    ):
        self._api_key = api_key or os.environ.get("XAI_API_KEY")
        self._base_url = os.environ.get("XAI_BASE_URL", base_url).rstrip("/")
        self._model = os.environ.get("XAI_MODEL", model)
        self._timeout = timeout_s

    async def sse_completion(
        self,
        body: dict,
        *,
        activity_call=None,
        kind: str = "completion",
    ) -> AsyncIterator[dict]:
        if not self._api_key:
            raise ValueError(
                "xAI provider requires an api_key. Set the XAI_API_KEY environment variable."
            )

        payload = {
            "model": self._model,
            "messages": body.get("messages", []),
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        # Map supported sampling parameters
        for k in ("temperature", "max_tokens", "top_p", "presence_penalty", "frequency_penalty"):
            if k in body:
                payload[k] = body[k]

        if kind in STRUCTURED_OUTPUTS:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": kind,
                    "strict": STRUCTURED_OUTPUTS[kind].get("strict", True),
                    "schema": STRUCTURED_OUTPUTS[kind]["json_schema"],
                },
            }
        elif "grammar" in body:
            log.warning("[%s] xAI provider does not support GBNF grammar. Dropping it.", kind)

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        n_msgs = len(payload["messages"])
        log.info("[%s] POST %s  messages=%d  model=%s", kind, url, n_msgs, self._model)

        if activity_call is not None:
            llm_activity.set_request(activity_call, payload)

        heartbeat_stop, hb_task = start_heartbeat(kind)
        progress = ProgressLogger(kind)

        start = time.monotonic()
        first_token_at: float | None = None
        bad_chunks = 0

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
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
                        piece = delta.get("content")

                        if piece and first_token_at is None:
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
        except httpx.HTTPStatusError as e:
            await e.response.aread()
            log.error("[%s] xAI API error %d: %s", kind, e.response.status_code, e.response.text)
            raise
        finally:
            heartbeat_stop.set()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

    def get_default_prompt(self, kind: str) -> str:
        # Minimal placeholder for cloud providers
        return f"You are a helpful assistant for {kind}."
            if bad_chunks:
                log.warning("[%s] dropped %d malformed SSE chunks", kind, bad_chunks)
