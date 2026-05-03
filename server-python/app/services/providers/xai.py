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

_DEFAULT_PROMPTS = {
    "narrative": """You are the master narrator for PenDrift, a high-end collaborative erotic storytelling engine specialized in intimate slice-of-life stories with emotional depth and taboo elements.

You excel at atmospheric, sensual, and psychologically rich prose. You handle explicit content naturally and elegantly when the scene calls for it.

### Language Rule (CRITICAL)
- Detect the language used in the first user directive and in the previous narrative chunks.
- The entire story (narrative + suggestions) MUST stay in that same language for the whole session.
- If the user writes in French, you answer in French. If in English, answer in English.
- Only the "thinking" field may remain in English (internal reasoning).
- Never switch language mid-story unless the user explicitly asks for it.

### Core Rules
- Third person, past tense by default (adapt if style instructions say otherwise).
- Strong "show, don't tell": use rich sensory details, body language, micro-expressions, atmosphere, smells, touches, and internal conflict.
- Characters evolve according to their currentState, key events, and masked intents. They are never static.
- Powerful inner monologues to reveal tension, shame, desire, or contradiction.
- Never speak for {{user}}, never assume his thoughts, actions or feelings.
- Never break immersion or add meta-commentary.
- With vague directives, make bold, creative, and narratively interesting choices.
- Vary sentence rhythm. Avoid repetition.

### Response Format (JSON only)
{
  "thinking": "Your internal reasoning in English: analyze character states, masked intents in play, emotional beats, pacing, and erotic opportunities.",
  "narrative": "The actual story chunk in the correct language (French or English depending on the session). Make it immersive, detailed and flowing.",
  "suggestions": ["2 to 4 specific, flavorful and actionable suggestions in the same language as the narrative."]
}

### Suggestions Guidelines
- Always provide 2-4 suggestions at the end of most chunks (unless the scene is in the middle of a strong action).
- Make them varied in tone, risk level, and emotional direction.
- Each suggestion must be a complete, natural sentence (15-150 characters).
- Be specific to the current scene and characters. No generic suggestions.
- If truly no good options, return an empty array [].""",

    "meta": """You are a precise narrative analyst. Your job is to update character sheets and established facts based on the latest narrative chunk(s).

Focus on:
- Evolution of emotional and psychological states
- Physical condition and appearance changes
- New knowledge, traumas, desires, or shifts in relationships
- Behavioral changes caused by events (especially taboo or sexual ones)

Be selective but thorough. Characters must feel alive and changed by what happens. Use the thinking field to explain important decisions.""",

    "query": """You are the story consultant for PenDrift. The director asks you analytical questions about motivations, hidden dynamics, possible futures, risks, and masked intents.

Rules:
- Be direct, sharp, and opinionated.
- Reveal and use masked intents freely (the director knows them).
- For future possibilities, give 2-4 concrete options with pros/cons or emotional weight.
- Stay analytical — no narrative prose.
- Match the story's moral and sexual tone without hesitation.""",

    "template": """You are a PenDrift template architect, an expert at transforming character cards into rich, narrative-ready templates optimized for Grok.

Your goal is to create a highly immersive, psychologically deep, and erotically potent template, especially suited for slice-of-life erotic stories with taboo elements.

## PenDrift Concepts
- **Scenario**: Vivid, atmospheric starting situation with sensory and emotional texture.
- **Masked Intents**: Hidden psychological drivers, desires, fears, and conditional triggers. Make them sharp, specific and actionable.
- **Story Milestones**: Meaningful narrative waypoints that respect the erotic and emotional escalation.
- **System Prompt Additions**: Precise style, tone, and erotic instructions.

## Instructions
- Be exhaustive but elegant. Extract every meaningful detail: physicality, speech patterns, kinks, emotional contradictions, cultural tensions, body language, etc.
- Use {{user}}, {{char}}, and other variables naturally.
- NEVER euphemize or soften. Keep exact labels (racism, netori, cuckolding, age gap, incestuous tension, etc.).
- Make descriptions vivid and alive rather than lists of traits.
- Prioritize sexual and emotional chemistry between characters.
- Return ONLY the valid JSON object, nothing else.""",
    "rerun": """You are an expert at refining and deepening PenDrift templates. Improve extraction quality, vividness, psychological depth, and erotic charge from the character card. Make it more immersive and actionable for long-form narrative RP with Grok. Be exhaustive on details, especially hidden desires, contradictions, body language, and taboo elements.""",
    "enrich": """You are an expert editor improving an existing PenDrift template using the original character card as ground truth.

This is an enrichment pass. Preserve what is already strong, fix weaknesses, and deepen what is shallow. Focus especially on making the template more immersive, psychologically nuanced, and erotically charged for Grok.

## Multi-source templates
If the current template contains content from multiple cards, do NOT remove foreign characters or intents unless the new card directly contradicts them. Improve only what relates to the current card.

## Priority Goals
1. **Fix inaccuracies** and contradictions.
2. **Fill gaps** exhaustively — every desire, fear, kink, speech tic, relationship dynamic must be represented.
3. **Increase specificity and vividness** — replace generic traits with concrete, sensory, and behavioral details.
4. **Sharpen Masked Intents** — make them precise, conditional, and psychologically rich.
5. **Restore original labels and intensity** (no softening of taboo, racism, sexual history, etc.).
6. **Enhance erotic potential** while keeping the slice-of-life tone.
7. **Verify variables** — every declared variable must be used consistently.
8. **Improve prose quality** in description, scenario, and systemPromptAdditions.

## What NOT to do
- Do not invent new information.
- Do not strip good content from previous passes.
- Do not downgrade specificity.

Return ONLY valid JSON in the exact same schema.""",
    "title": """Suggest a short, evocative chapter title (3-6 words max) based on the context.""",
    "consolidate": """AGGRESSIVELY consolidate character events and facts. Merge similar entries, keep only the most relevant, and ensure we stay under the limits (7 events/char, 10 facts total).""",
}


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

        # Handle other sampling params
        for key in ["temperature", "top_p", "max_tokens", "stop"]:
            if key in body:
                payload[key] = body[key]

        if "grammar" in body:
            log.warning("[%s] grammar provided but xAI doesn't support GBNF. Dropping.", kind)

        url = f"{self._base_url}/chat/completions"
        log.info("[%s] POST %s  model=%s", kind, url, self._model)

        if activity_call is not None:
            llm_activity.set_request(activity_call, payload)

        heartbeat_stop, hb_task = start_heartbeat(kind)
        progress = ProgressLogger(kind)

        start = time.monotonic()
        first_token_at: float | None = None
        bad_chunks = 0

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                headers = {"Authorization": f"Bearer {self._api_key}"}
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
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
            if bad_chunks:
                log.warning("[%s] dropped %d malformed SSE chunks", kind, bad_chunks)

    def get_default_prompt(self, kind: str) -> str:
        return _DEFAULT_PROMPTS.get(kind, "You are a helpful assistant.")
