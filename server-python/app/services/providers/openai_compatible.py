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

from typing import AsyncIterator


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
        self._api_key = api_key
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
        # The body we receive carries `grammar` (GBNF) — OpenAI's API doesn't
        # speak GBNF. Until JSON Schema versions of the grammars exist (see
        # module docstring), refuse with a precise error so the caller knows
        # exactly what's missing.
        if "grammar" in body:
            raise NotImplementedError(
                "OpenAI provider doesn't accept GBNF grammar. PenDrift's grammars "
                "in app/utils/grammars.py need JSON Schema equivalents before this "
                "provider can serve narrative/meta/etc. calls. See "
                "providers/openai_compatible.py module docstring for the migration "
                "plan."
            )
        if not self._api_key:
            raise NotImplementedError(
                "OpenAI provider requires an api_key. Wire it in via the preset "
                "settings (e.g., settings.providerConfig.apiKey) and pass to "
                "get_provider('openai', api_key=..., base_url=..., model=...)."
            )
        raise NotImplementedError(
            "OpenAICompatibleProvider.sse_completion is not implemented yet — "
            "this is scaffolding. See module docstring for what's needed."
        )
        # The next line is unreachable; it's here so the function is a valid
        # async generator (otherwise the `raise NotImplementedError` makes it
        # a regular async function, which would mismatch the Protocol).
        yield {"type": "delta", "text": ""}  # pragma: no cover
