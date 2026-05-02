"""Streaming narrative generation with progressive field parsing.

Because grammar forces the output shape:
  {"thinking": "...", "type": "narrative", "narrative": "...", "suggestions": [...]}

we parse the SSE stream chunk-by-chunk and emit semantic events so the
frontend can show:
  - Live thinking text as the model reasons
  - Switch to live narrative when narrative starts
  - Final suggestions once parsed
  - Chunk metadata (stats, model) when done

Event types yielded:
  thinking_start, thinking_chunk(text), thinking_done
  type_resolved(value)
  narrative_start, narrative_chunk(text), narrative_done
  suggestions(list)
  done(full_result)
  error(message)
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
from app.utils.grammars import NARRATIVE_GRAMMAR, QUERY_GRAMMAR

log = logging.getLogger("pendrift.llm_stream")


# JSON simple-escape decoding, used while streaming live chars
_ESCAPE_MAP = {
    "n": "\n", "t": "\t", "r": "\r",
    '"': '"', "\\": "\\", "/": "/",
    "b": "\b", "f": "\f",
}


class _StructuredParser:
    """Walk through the grammar-forced JSON character-by-character and
    emit events as fields start/stream/finish.

    Holds back the trailing byte if it could be the start of an escape
    sequence so we can decode `\n` etc. into a real newline before
    emitting it to the frontend.
    """

    # Default markers for the narrative grammar. Override via constructor.
    _DEFAULT_MARKERS = [
        ('"thinking":"', "thinking", True),    # inside string
        (',"type":"', "type", True),
        (',"narrative":"', "narrative", True),
        (',"suggestions":', "suggestions", False),  # array (or "[]")
    ]

    def __init__(self, markers=None):
        self._MARKERS = markers if markers is not None else self._DEFAULT_MARKERS
        self.buffer = ""
        self.cursor = 0
        self.current_field: str | None = None
        self.in_string = False
        self.escape_pending = False
        self._next_marker_idx = 0

    def push(self, delta: str) -> list[dict]:
        self.buffer += delta
        events: list[dict] = []

        while True:
            if self.current_field is not None and self.in_string:
                # Stream chars from the current string-valued field.
                produced = False
                while self.cursor < len(self.buffer):
                    ch = self.buffer[self.cursor]
                    if self.escape_pending:
                        decoded = _ESCAPE_MAP.get(ch, ch)
                        events.append({"type": f"{self.current_field}_chunk", "text": decoded})
                        self.escape_pending = False
                        self.cursor += 1
                        produced = True
                        continue
                    if ch == "\\":
                        # Possible escape — only consume if we have the next byte too
                        if self.cursor + 1 >= len(self.buffer):
                            # Wait for next chunk before deciding
                            return events
                        self.escape_pending = True
                        self.cursor += 1
                        continue
                    if ch == '"':
                        # End of string-valued field
                        events.append({"type": f"{self.current_field}_done"})
                        self.in_string = False
                        self.current_field = None
                        self.cursor += 1
                        break
                    events.append({"type": f"{self.current_field}_chunk", "text": ch})
                    self.cursor += 1
                    produced = True
                else:
                    # Buffer fully consumed, still in string — wait for more
                    return events
                # Loop back to look for next marker
                continue

            # Looking for the next field marker
            if self._next_marker_idx >= len(self._MARKERS):
                return events
            marker, field_name, is_string_value = self._MARKERS[self._next_marker_idx]
            pos = self.buffer.find(marker, self.cursor)
            if pos < 0:
                return events  # not yet
            self.cursor = pos + len(marker)
            self._next_marker_idx += 1
            self.current_field = field_name
            self.in_string = is_string_value
            events.append({"type": f"{field_name}_start"})
            if not is_string_value:
                # `suggestions` is an array — we don't stream its content live;
                # we'll parse it at the end. Mark current_field as None now.
                self.current_field = None

        return events


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
) -> AsyncIterator[dict]:
    """Stream a grammar-constrained narrative generation as a sequence of
    semantic events. The final event is always either `done` or `error`."""
    base = get_base_url()
    url = f"{base}/v1/chat/completions"

    body: dict = {
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
        "grammar": NARRATIVE_GRAMMAR,
    }
    for k, v in (
        ("temperature", temperature), ("max_tokens", max_tokens),
        ("top_p", top_p), ("top_k", top_k), ("min_p", min_p),
        ("repeat_penalty", repeat_penalty),
        ("presence_penalty", presence_penalty),
        ("frequency_penalty", frequency_penalty),
        ("seed", seed),
    ):
        if v is not None:
            body[k] = v

    # Activity tracking + cancellation hook
    call = llm_activity.register("narrative", session_id)
    llm_activity.attach_task(call, asyncio.current_task())

    parser = _StructuredParser()
    full_buffer = ""
    usage: dict = {}
    model_name = ""
    first_token_at: float | None = None
    chunk_count = 0
    token_count = 0
    thinking_tokens = 0
    narrative_tokens = 0

    log.info("[narrative-stream] POST messages=%d max_tokens=%s",
             len(messages), max_tokens or "-")

    llm_activity.set_request(call, body)

    try:
        llm_activity.mark_running(call)
        yield {"type": "started", "callId": call.id}

        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", url, json=body) as resp:
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
                        continue
                    chunk_count += 1

                    if chunk.get("model"):
                        model_name = chunk["model"]
                    if chunk.get("usage"):
                        usage = chunk["usage"]

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if not piece:
                        continue

                    if first_token_at is None:
                        first_token_at = time.time()
                        log.info("[narrative-stream] first token after %dms",
                                 int((time.time() - call.running_at) * 1000))

                    full_buffer += piece
                    token_count += 1
                    llm_activity.update_progress(call, tokens=token_count, first_token_at=first_token_at)

                    parsed_events = parser.push(piece)
                    # Approximate per-field token count: +1 per llama-server SSE chunk
                    # that contributed to a given field
                    fields_touched = {ev["type"].rsplit("_", 1)[0]
                                      for ev in parsed_events
                                      if ev["type"].endswith("_chunk")}
                    if "thinking" in fields_touched:
                        thinking_tokens += 1
                    if "narrative" in fields_touched:
                        narrative_tokens += 1
                    if fields_touched:
                        llm_activity.update_field_tokens(
                            call,
                            thinking=thinking_tokens if "thinking" in fields_touched or call.thinking_tokens else None,
                            narrative=narrative_tokens if "narrative" in fields_touched or call.narrative_tokens else None,
                        )

                    for event in parsed_events:
                        yield event

        # Stream finished. Parse final JSON.
        try:
            result = json.loads(full_buffer)
        except json.JSONDecodeError as e:
            llm_activity.mark_done(call, error=f"Invalid JSON: {e}", raw_response=full_buffer)
            yield {"type": "error", "message": f"Invalid JSON from model: {e.msg}"}
            return

        stats = {
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
        }
        llm_activity.mark_done(call, stats=stats, model=model_name, raw_response=full_buffer)

        # Filter out filler/junk entries the model sometimes pads suggestions
        # with ("," / " " / very short strings that aren't real suggestions).
        cleaned_suggestions = [
            s for s in (result.get("suggestions") or [])
            if isinstance(s, str) and len(s.strip()) >= 10
        ]

        yield {"type": "type_resolved", "value": result.get("type", "narrative")}
        if cleaned_suggestions:
            yield {"type": "suggestions", "items": cleaned_suggestions}
        yield {
            "type": "done",
            "result": {
                "thinking": result.get("thinking", ""),
                "type": result.get("type", "narrative"),
                "narrative": result.get("narrative", ""),
                "suggestions": cleaned_suggestions,
                "modelName": model_name,
                "stats": stats,
                "raw": full_buffer,
            },
        }

    except asyncio.CancelledError:
        llm_activity.mark_done(call, error="cancelled", raw_response=full_buffer or None)
        yield {"type": "error", "message": "cancelled"}
        raise
    except httpx.HTTPError as e:
        log.error("[narrative-stream] HTTP error: %s", e)
        llm_activity.mark_done(call, error=str(e))
        yield {"type": "error", "message": str(e)}
    except Exception as e:
        log.exception("[narrative-stream] unexpected error")
        llm_activity.mark_done(call, error=str(e))
        yield {"type": "error", "message": str(e)}


# ── Query (Ask the Narrator) streaming ──────────────────

_QUERY_MARKERS = [
    ('"thinking":"', "thinking", True),
    (',"answer":"', "answer", True),
]


async def stream_query(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    seed: int | None = None,
    session_id: str | None = None,
):
    """Stream a Q&A consultation. Emits events:
      thinking_start, thinking_chunk{text}, thinking_done,
      answer_start, answer_chunk{text}, answer_done,
      done{result: {thinking, answer, ...}}, error{message}
    """
    base = get_base_url()
    url = f"{base}/v1/chat/completions"

    body: dict = {
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
        "grammar": QUERY_GRAMMAR,
    }
    for k, v in (
        ("temperature", temperature), ("max_tokens", max_tokens),
        ("top_p", top_p), ("top_k", top_k), ("seed", seed),
    ):
        if v is not None:
            body[k] = v

    call = llm_activity.register("query", session_id)
    llm_activity.attach_task(call, asyncio.current_task())
    llm_activity.set_request(call, body)

    parser = _StructuredParser(markers=_QUERY_MARKERS)
    full_buffer = ""
    usage: dict = {}
    model_name = ""
    first_token_at: float | None = None
    token_count = 0

    log.info("[query-stream] POST messages=%d max_tokens=%s", len(messages), max_tokens or "-")

    try:
        llm_activity.mark_running(call)
        yield {"type": "started", "callId": call.id}

        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", url, json=body) as resp:
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
                        continue
                    if chunk.get("model"):
                        model_name = chunk["model"]
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if not piece:
                        continue
                    if first_token_at is None:
                        first_token_at = time.time()
                    full_buffer += piece
                    token_count += 1
                    llm_activity.update_progress(call, tokens=token_count, first_token_at=first_token_at)
                    for event in parser.push(piece):
                        yield event

        try:
            result = json.loads(full_buffer)
        except json.JSONDecodeError as e:
            llm_activity.mark_done(call, error=f"Invalid JSON: {e}", raw_response=full_buffer)
            yield {"type": "error", "message": f"Invalid JSON from model: {e.msg}"}
            return

        stats = {
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
        }
        llm_activity.mark_done(call, stats=stats, model=model_name, raw_response=full_buffer)
        yield {
            "type": "done",
            "result": {
                "thinking": result.get("thinking", ""),
                "answer": result.get("answer", ""),
                "modelName": model_name,
                "stats": stats,
            },
        }
    except asyncio.CancelledError:
        llm_activity.mark_done(call, error="cancelled", raw_response=full_buffer or None)
        yield {"type": "error", "message": "cancelled"}
        raise
    except httpx.HTTPError as e:
        llm_activity.mark_done(call, error=str(e))
        yield {"type": "error", "message": str(e)}
    except Exception as e:
        log.exception("[query-stream] unexpected error")
        llm_activity.mark_done(call, error=str(e))
        yield {"type": "error", "message": str(e)}
