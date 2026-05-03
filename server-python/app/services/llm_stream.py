"""Streaming narrative + query generation with progressive field parsing.

Because grammar forces the output JSON into a fixed shape, we can parse the
SSE stream from the provider character-by-character and emit semantic events
as each field starts / streams / finishes — so the UI shows live thinking
text, then live narrative, etc.

Event types yielded:
  started{callId}
  thinking_start, thinking_chunk{text}, thinking_done
  type_resolved{value}                      (narrative only)
  narrative_start, narrative_chunk{text}, narrative_done
  answer_start, answer_chunk{text}, answer_done   (query only)
  suggestions{items}
  done{result: {...}}
  error{message}

The whole LLM-call boilerplate (provider selection, model autoload, lock,
activity register, mark_done, error/cancel handling) lives in
`services/llm.py::run_llm_stream`. This file only contains the
grammar-aware structured parser + the per-flow event massage.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator

from app.services.llm import run_llm_stream

log = logging.getLogger("pendrift.llm_stream")


# JSON simple-escape decoding, used while streaming live chars from the
# grammar-constrained JSON output.
_ESCAPE_MAP = {
    "n": "\n", "t": "\t", "r": "\r",
    '"': '"', "\\": "\\", "/": "/",
    "b": "\b", "f": "\f",
}


class _StructuredParser:
    """Walk through grammar-forced JSON character-by-character and emit
    events as fields start/stream/finish.

    Holds back the trailing byte if it could be the start of an escape
    sequence so we can decode `\\n` etc. into a real newline before
    emitting it to the frontend.
    """

    # Each marker is (field_name, is_string_value).
    _DEFAULT_TASK_MAP = {
        "narrative": [
            ("thinking", True),
            ("type", True),
            ("narrative", True),
            ("suggestions", False),
        ],
        "query": [
            ("thinking", True),
            ("answer", True),
        ],
    }

    def __init__(self, kind: str = "narrative", custom_markers=None):
        self.buffer = ""
        self.cursor = 0
        self.current_field: str | None = None
        self.in_string = False
        self.escape_pending = False
        self._next_field_idx = 0
        self._FIELDS = custom_markers or self._DEFAULT_TASK_MAP.get(kind, self._DEFAULT_TASK_MAP["narrative"])

    def _build_marker_regex(self, field_name: str, is_string_value: bool, is_first: bool) -> str:
        f = re.escape(f'"{field_name}"')
        prefix = r'\{' if is_first else r','
        suffix = r'"' if is_string_value else ''
        return rf'{prefix}\s*{f}\s*:\s*{suffix}'

    def push(self, delta: str) -> list[dict]:
        self.buffer += delta
        events: list[dict] = []

        while True:
            if self.current_field is not None and self.in_string:
                while self.cursor < len(self.buffer):
                    ch = self.buffer[self.cursor]
                    if self.escape_pending:
                        decoded = _ESCAPE_MAP.get(ch, ch)
                        events.append({"type": f"{self.current_field}_chunk", "text": decoded})
                        self.escape_pending = False
                        self.cursor += 1
                        continue
                    if ch == "\\":
                        if self.cursor + 1 >= len(self.buffer):
                            return events
                        self.escape_pending = True
                        self.cursor += 1
                        continue
                    if ch == '"':
                        events.append({"type": f"{self.current_field}_done"})
                        self.in_string = False
                        self.current_field = None
                        self.cursor += 1
                        break
                    events.append({"type": f"{self.current_field}_chunk", "text": ch})
                    self.cursor += 1
                else:
                    return events
                continue

            # Looking for the next field marker
            if self._next_field_idx >= len(self._FIELDS):
                return events
            field_name, is_string_value = self._FIELDS[self._next_field_idx]
            regex = self._build_marker_regex(field_name, is_string_value, self._next_field_idx == 0)
            match = re.search(regex, self.buffer[self.cursor:])
            if not match:
                return events
            self.cursor += match.end()
            self._next_field_idx += 1
            self.current_field = field_name
            self.in_string = is_string_value
            events.append({"type": f"{field_name}_start"})
            if not is_string_value:
                self.current_field = None


# ── Narrative streaming ─────────────────────────────────
async def stream_narrative(
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
    settings: dict | None = None,
) -> AsyncIterator[dict]:
    """Stream a grammar-constrained narrative as a sequence of semantic
    events. The final event is always either `done` or `error`."""
    parser = _StructuredParser(kind="narrative")
    full_buffer = ""
    usage: dict = {}
    model_name = ""
    # Per-field text accumulators — used to assemble a partial result if the
    # generation is cancelled mid-stream so the caller can still save what
    # we got as a normal chunk.
    field_text: dict[str, list[str]] = {"thinking": [], "type": [], "narrative": []}
    thinking_started_externally = False

    log.info("[narrative-stream] POST messages=%d max_tokens=%s", len(messages), max_tokens or "-")

    try:
        async for ev in run_llm_stream(
            messages,
            settings=settings,
            kind="narrative-stream",
            session_id=session_id,
            temperature=temperature, max_tokens=max_tokens,
            top_p=top_p, top_k=top_k, min_p=min_p,
            repeat_penalty=repeat_penalty,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            seed=seed,
        ):
            t = ev["type"]
            if t == "started":
                yield ev
            elif t == "delta":
                piece = ev["text"]
                full_buffer += piece
                for parsed_ev in parser.push(piece):
                    if parsed_ev["type"].endswith("_chunk"):
                        fname = parsed_ev["type"].rsplit("_", 1)[0]
                        if fname in field_text:
                            field_text[fname].append(parsed_ev["text"])
                    yield parsed_ev
            elif t == "thinking_delta":
                # External providers (Grok, OpenAI o-series) stream chain-of-
                # thought via a separate `reasoning_content` channel instead
                # of inside the grammar JSON. Surface it as thinking_*
                # events so the UI shows it the same way.
                piece = ev["text"]
                if not thinking_started_externally:
                    thinking_started_externally = True
                    yield {"type": "thinking_start"}
                field_text["thinking"].append(piece)
                yield {"type": "thinking_chunk", "text": piece}
            elif t == "model":
                model_name = ev["name"]
            elif t == "usage":
                usage = ev["data"]
            elif t == "llm_done":
                # Stream finished — parse final JSON and emit semantic done.
                try:
                    result = json.loads(full_buffer)
                except json.JSONDecodeError as e:
                    yield {"type": "error", "message": f"Invalid JSON from model: {e.msg}"}
                    return

                cleaned_suggestions = [
                    s for s in (result.get("suggestions") or [])
                    if isinstance(s, str) and len(s.strip()) >= 10
                ]
                stats = ev["stats"]
                yield {"type": "type_resolved", "value": result.get("type", "narrative")}
                if cleaned_suggestions:
                    yield {"type": "suggestions", "items": cleaned_suggestions}
                yield {
                    "type": "done",
                    "result": {
                        "thinking": result.get("thinking", "") or "".join(field_text["thinking"]),
                        "type": result.get("type", "narrative"),
                        "narrative": result.get("narrative", ""),
                        "suggestions": cleaned_suggestions,
                        "modelName": model_name,
                        "stats": stats,
                        "raw": full_buffer,
                    },
                }

    except asyncio.CancelledError:
        # User cancelled mid-stream. Treat what we got (partial thinking
        # + partial narrative) as a finished chunk so the caller saves it
        # like any other generation. Activity stays marked `cancelled`.
        partial_thinking = "".join(field_text["thinking"])
        partial_type = "".join(field_text["type"]) or "narrative"
        partial_narrative = "".join(field_text["narrative"])
        stats = {
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
            "cancelled": True,
        }
        yield {
            "type": "done",
            "result": {
                "thinking": partial_thinking,
                "type": partial_type,
                "narrative": partial_narrative,
                "suggestions": [],
                "modelName": model_name,
                "stats": stats,
                "raw": full_buffer,
                "cancelled": True,
            },
        }
        raise
    except Exception as e:
        log.exception("[narrative-stream] unexpected error")
        yield {"type": "error", "message": str(e)}


# ── Query (Ask the Narrator) streaming ──────────────────
async def stream_query(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    seed: int | None = None,
    session_id: str | None = None,
    settings: dict | None = None,
) -> AsyncIterator[dict]:
    """Stream an Ask-the-Narrator analytical Q&A. Emits:
      thinking_start, thinking_chunk{text}, thinking_done,
      answer_start, answer_chunk{text}, answer_done,
      done{result}, error{message}
    """
    parser = _StructuredParser(kind="query")
    full_buffer = ""
    usage: dict = {}
    model_name = ""
    thinking_started_externally = False

    log.info("[query-stream] POST messages=%d max_tokens=%s", len(messages), max_tokens or "-")

    try:
        async for ev in run_llm_stream(
            messages,
            settings=settings,
            kind="query-stream",
            session_id=session_id,
            temperature=temperature, max_tokens=max_tokens,
            top_p=top_p, top_k=top_k, seed=seed,
        ):
            t = ev["type"]
            if t == "started":
                yield ev
            elif t == "delta":
                piece = ev["text"]
                full_buffer += piece
                for parsed_ev in parser.push(piece):
                    yield parsed_ev
            elif t == "thinking_delta":
                if not thinking_started_externally:
                    thinking_started_externally = True
                    yield {"type": "thinking_start"}
                yield {"type": "thinking_chunk", "text": ev["text"]}
            elif t == "model":
                model_name = ev["name"]
            elif t == "usage":
                usage = ev["data"]
            elif t == "llm_done":
                try:
                    result = json.loads(full_buffer)
                except json.JSONDecodeError as e:
                    yield {"type": "error", "message": f"Invalid JSON from model: {e.msg}"}
                    return
                yield {
                    "type": "done",
                    "result": {
                        "thinking": result.get("thinking", ""),
                        "answer": result.get("answer", ""),
                        "modelName": model_name,
                        "stats": ev["stats"],
                    },
                }

    except asyncio.CancelledError:
        yield {"type": "error", "message": "cancelled"}
        raise
    except Exception as e:
        log.exception("[query-stream] unexpected error")
        yield {"type": "error", "message": str(e)}
