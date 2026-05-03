"""OpenAI-compatible API provider — SCAFFOLDING ONLY, not yet wired.

This stub documents what's needed to swap PenDrift's inference backend from
local llama-server to a hosted OpenAI-compatible API (OpenAI proper, xAI/Grok,
Together, Fireworks, OpenRouter, Mistral La Plateforme, Groq, ...).

To finish this provider:

1. **Auth + base URL config** — accept `api_key`, `base_url`, `model` in the
   constructor; read from preset settings (e.g., `provider: "openai"`,
   `apiKey: ...`, `model: "gpt-4o"`, `baseUrl: "https://api.openai.com/v1"`).

2. **Body translation** —
   - Drop sampling params the API doesn't accept: `min_p`, `repeat_penalty`,
     and (for OpenAI proper) `top_k`. Log a warning when dropping.
   - Force `model` field from config (overriding any caller-passed model).
   - Drop `chat_template_kwargs` (llama-server-specific).

3. **Structured output translation** — this is the real work. PenDrift's
   grammars in `app/utils/grammars.py` are GBNF (llama.cpp). OpenAI-compatible
   APIs use JSON Schema instead. Two paths:
     a) Maintain dual definitions: keep `grammars.py` (GBNF) + new
        `json_schemas.py` (JSON Schema). The provider that accepts
        body["grammar"] = GBNF would receive body["responseSchema"] = JSON
        Schema dict instead, and translate to whatever the API wants
        (`response_format: {type: "json_schema", json_schema: ...}` for
        OpenAI; `responseSchema` for Gemini; tool-forcing for Anthropic).
     b) Generate JSON Schema from GBNF programmatically — possible for
        simple grammars but not all GBNF features map cleanly. Skipped.

   The PenDrift caller layer (`_build_body`) currently sets `body["grammar"]`
   = GBNF string. To support both, callers should pass an abstract
   structured-output spec the provider translates. Suggested:
     body["structuredOutput"] = {"format": "gbnf", "value": "<grammar text>"}
                              | {"format": "jsonSchema", "value": {...}}
   then the LlamaServerProvider keeps the gbnf path, and this provider
   reads jsonSchema (or refuses the call if format is gbnf).

4. **SSE format** — most OpenAI-compatible APIs use the same SSE shape as
   llama-server (`data: {...}\\n\\n` with `choices[0].delta.content`), so the
   parsing in `llama_server.py` is mostly portable. Anthropic uses a
   different event-typed SSE format and would need its own provider.

5. **Auth + retry** — OpenAI-style `Authorization: Bearer <key>` header,
   exponential backoff on 429/503, request id logging for debugging.

6. **Cost / token accounting** — usage chunks come back the same way; no
   change needed for activity tracking.
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

log = logging.getLogger("pendrift.providers.openai")

class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_s: float = 600.0,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
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
                "OpenAI provider requires an api_key. Set the OPENAI_API_KEY environment variable."
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
            log.warning("[%s] OpenAI provider does not support GBNF grammar. Dropping it.", kind)

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
            log.error("[%s] OpenAI API error %d: %s", kind, e.response.status_code, e.response.text)
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

