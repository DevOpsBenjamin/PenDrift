"""Streaming narrative generation with progressive field parsing.

Because we know the grammar structure is always:
  {"thinking": "...", "type": "...", "narrative": "...", "suggestions": [...]}

We can parse the SSE stream token-by-token and emit events as fields complete:
  1. THINKING_START → tokens flow into thinking
  2. THINKING_DONE  → thinking field complete, we know the type
  3. NARRATIVE_START → tokens flow into narrative (show in UI live)
  4. NARRATIVE_DONE  → narrative complete
  5. SUGGESTIONS     → parsed suggestions array
  6. DONE            → full JSON available

The frontend shows:
  - A "thinking" spinner/collapse while thinking streams
  - The narrative appearing token-by-token
  - Suggestions as buttons when they arrive
"""
from __future__ import annotations

import json
import logging
from enum import Enum
from typing import AsyncIterator

import httpx

from app.services.llm_process import get_base_url
from app.utils.grammars import NARRATIVE_GRAMMAR

log = logging.getLogger("pendrift.llm_stream")


class StreamPhase(str, Enum):
    THINKING_START = "thinking_start"
    THINKING_TOKEN = "thinking_token"
    THINKING_DONE = "thinking_done"
    TYPE_RESOLVED = "type_resolved"
    NARRATIVE_START = "narrative_start"
    NARRATIVE_TOKEN = "narrative_token"
    NARRATIVE_DONE = "narrative_done"
    SUGGESTIONS = "suggestions"
    DONE = "done"
    ERROR = "error"


async def stream_narrative(
    messages: list[dict],
    **kwargs,
) -> AsyncIterator[dict]:
    """Stream a grammar-constrained narrative generation, yielding phase events.

    Each yielded dict has:
        {"phase": StreamPhase, "content": str, "data": optional dict}
    """
    base = get_base_url()
    url = f"{base}/v1/chat/completions"

    body: dict = {
        "messages": messages,
        "stream": True,
        "grammar": NARRATIVE_GRAMMAR,
    }
    for k in ("temperature", "max_tokens", "top_p", "top_k", "min_p",
              "repeat_penalty", "presence_penalty", "frequency_penalty", "seed"):
        if kwargs.get(k) is not None:
            body[k] = kwargs[k]

    full_text = ""
    current_phase = None

    # Track which JSON field we're inside by counting structure
    # The grammar forces this order: thinking → type → narrative → suggestions
    field_order = ["thinking", "type", "narrative", "suggestions"]
    current_field_idx = -1
    in_string = False
    escape_next = False
    brace_depth = 0
    bracket_depth = 0

    try:
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
                    token = delta.get("content", "")
                    if not token:
                        continue

                    full_text += token

                    # Detect field transitions by watching for key patterns
                    # The grammar forces: {"thinking": "...", "type": "...", ...}
                    for char in token:
                        if escape_next:
                            escape_next = False
                            # Emit token if we're in a content field
                            if current_field_idx >= 0 and in_string:
                                field = field_order[current_field_idx]
                                if field == "thinking" and current_phase != StreamPhase.THINKING_DONE:
                                    if current_phase != StreamPhase.THINKING_START:
                                        current_phase = StreamPhase.THINKING_START
                                        yield {"phase": StreamPhase.THINKING_START, "content": ""}
                                    yield {"phase": StreamPhase.THINKING_TOKEN, "content": char}
                                elif field == "narrative" and current_phase != StreamPhase.NARRATIVE_DONE:
                                    if current_phase not in (StreamPhase.NARRATIVE_START, StreamPhase.NARRATIVE_TOKEN):
                                        current_phase = StreamPhase.NARRATIVE_START
                                        yield {"phase": StreamPhase.NARRATIVE_START, "content": ""}
                                    yield {"phase": StreamPhase.NARRATIVE_TOKEN, "content": char}
                            continue

                        if char == "\\":
                            escape_next = True
                            continue

                        if char == '"':
                            in_string = not in_string
                            # Detect field key transitions
                            if not in_string:
                                # Check if we just closed a key that matches our next expected field
                                for i, field in enumerate(field_order):
                                    if i > current_field_idx and full_text.rstrip().endswith(f'"{field}"'):
                                        current_field_idx = i
                                        break
                            continue

                        if in_string and current_field_idx >= 0:
                            field = field_order[current_field_idx]
                            if field == "thinking" and current_phase != StreamPhase.THINKING_DONE:
                                if current_phase != StreamPhase.THINKING_START:
                                    current_phase = StreamPhase.THINKING_START
                                    yield {"phase": StreamPhase.THINKING_START, "content": ""}
                                yield {"phase": StreamPhase.THINKING_TOKEN, "content": char}
                            elif field == "narrative" and current_phase != StreamPhase.NARRATIVE_DONE:
                                if current_phase not in (StreamPhase.NARRATIVE_START, StreamPhase.NARRATIVE_TOKEN):
                                    current_phase = StreamPhase.NARRATIVE_START
                                    yield {"phase": StreamPhase.NARRATIVE_START, "content": ""}
                                yield {"phase": StreamPhase.NARRATIVE_TOKEN, "content": char}

    except Exception as e:
        yield {"phase": StreamPhase.ERROR, "content": str(e)}
        return

    # Parse the complete JSON
    try:
        result = json.loads(full_text)
    except json.JSONDecodeError:
        yield {"phase": StreamPhase.ERROR, "content": f"Invalid JSON: {full_text[:200]}"}
        return

    yield {"phase": StreamPhase.THINKING_DONE, "content": result.get("thinking", "")}
    yield {"phase": StreamPhase.TYPE_RESOLVED, "content": result.get("type", "narrative")}
    yield {"phase": StreamPhase.NARRATIVE_DONE, "content": result.get("narrative", "")}
    if result.get("suggestions"):
        yield {"phase": StreamPhase.SUGGESTIONS, "content": "", "data": result["suggestions"]}
    yield {"phase": StreamPhase.DONE, "content": "", "data": result}
