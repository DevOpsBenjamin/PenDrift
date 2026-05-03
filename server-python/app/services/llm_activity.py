"""In-memory tracker for LLM call activity.

Every LLM call registers here on entry and updates on exit. Exposed via
`GET /api/llm/activity` for the frontend Activity view.

Each completed call also has its raw response persisted under
`data/llm-responses/` for later inspection. The metadata of completed calls
is appended to `data/llm-history.jsonl` so the history survives restarts —
the last `_MAX_HISTORY` entries are reloaded into the in-memory deque on
first snapshot read.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.config import DATA_DIR

log = logging.getLogger("pendrift.llm_activity")

_MAX_HISTORY = 100
_DUMP_DIR = DATA_DIR / "llm-responses"
_REQUEST_DIR = DATA_DIR / "llm-requests"
_HISTORY_PATH = DATA_DIR / "llm-history.jsonl"


@dataclass
class LlmCall:
    id: str
    kind: str
    session_id: str | None
    status: str  # "queued" | "running" | "success" | "error"
    started_at: float
    running_at: float | None = None
    ended_at: float | None = None
    duration_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Live-updated during SSE streaming:
    first_token_ms: int | None = None   # ms from running_at to first token
    tokens_per_sec: float | None = None
    # Per-field token breakdown (only set for grammar-streamed narrative calls)
    thinking_tokens: int | None = None
    narrative_tokens: int | None = None
    model: str | None = None
    error: str | None = None
    # Relative paths to the dumped request body and raw response
    request_file: str | None = None
    dump_file: str | None = None


_active: dict[str, LlmCall] = {}
_tasks: dict[str, asyncio.Task] = {}
_history: deque[dict] = deque(maxlen=_MAX_HISTORY)
_history_loaded = False


def attach_task(call: LlmCall, task: asyncio.Task | None) -> None:
    """Associate the asyncio task running this call so it can be cancelled."""
    if task is not None:
        _tasks[call.id] = task


def cancel(call_id: str) -> bool:
    """Cancel the task running this call. Returns True if a live task was hit."""
    task = _tasks.get(call_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def _load_history_from_disk() -> None:
    """Populate the in-memory deque from the JSONL log on first access."""
    global _history_loaded
    if _history_loaded:
        return
    _history_loaded = True
    if not _HISTORY_PATH.is_file():
        return
    try:
        with _HISTORY_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        log.warning("Could not read history file %s: %s", _HISTORY_PATH, e)
        return
    # File is oldest-first; iterate the last MAX_HISTORY lines so the deque
    # ends up with newest-at-left (matching live appendleft behavior).
    for line in lines[-_MAX_HISTORY:]:
        line = line.strip()
        if not line:
            continue
        try:
            _history.appendleft(json.loads(line))
        except json.JSONDecodeError:
            continue
    log.info("Loaded %d history entries from disk.", len(_history))


def _append_history_to_disk(entry: dict) -> None:
    def _do_append():
        try:
            _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _HISTORY_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("Could not append history entry to %s: %s", _HISTORY_PATH, e)
    
    # Run in a background thread to avoid blocking the event loop
    asyncio.get_event_loop().run_in_executor(None, _do_append)


def register(kind: str, session_id: str | None = None) -> LlmCall:
    call = LlmCall(
        id=str(uuid.uuid4()),
        kind=kind,
        session_id=session_id,
        status="queued",
        started_at=time.time(),
    )
    _active[call.id] = call
    return call


def mark_running(call: LlmCall) -> None:
    call.status = "running"
    call.running_at = time.time()


def update_progress(call: LlmCall, *, tokens: int, first_token_at: float | None) -> None:
    """Called from the SSE reader on each incoming chunk."""
    call.completion_tokens = tokens
    if first_token_at is not None and call.running_at is not None:
        if call.first_token_ms is None:
            call.first_token_ms = int((first_token_at - call.running_at) * 1000)
        elapsed_gen = time.time() - first_token_at
        if elapsed_gen > 0.1:
            call.tokens_per_sec = tokens / elapsed_gen


def update_field_tokens(call: LlmCall, *, thinking: int | None = None, narrative: int | None = None) -> None:
    """Per-field token counters for grammar-streamed narrative calls."""
    if thinking is not None:
        call.thinking_tokens = thinking
    if narrative is not None:
        call.narrative_tokens = narrative


def mark_done(
    call: LlmCall,
    *,
    stats: dict | None = None,
    model: str = "",
    error: str | None = None,
    raw_response: str | None = None,
) -> None:
    now = time.time()
    call.ended_at = now
    # duration measured from when it actually started running (or registration if never ran)
    start = call.running_at or call.started_at
    call.duration_ms = int((now - start) * 1000)
    if stats:
        call.prompt_tokens = stats.get("promptTokens")
        call.completion_tokens = stats.get("completionTokens")
    call.model = model
    if error is not None:
        call.status = "error"
        call.error = error
    else:
        call.status = "success"
    if raw_response:
        # Pre-compute the dump filename SYNC so call.dump_file is set before
        # asdict() snapshots it for the history. The actual file write is
        # offloaded to a thread to keep the event loop free.
        started = call.started_at or now
        ts = datetime.fromtimestamp(started).strftime("%Y%m%d-%H%M%S")
        filename = f"{ts}-{call.kind}-{call.id[:8]}.txt"
        call.dump_file = filename

        def _save_res():
            try:
                _DUMP_DIR.mkdir(parents=True, exist_ok=True)
                path = _DUMP_DIR / filename
                path.write_text(raw_response, encoding="utf-8")
            except OSError as e:
                log.warning("Failed to dump LLM response for call %s: %s", call.id, e)
        asyncio.get_event_loop().run_in_executor(None, _save_res)
    entry = asdict(call)
    _history.appendleft(entry)
    _append_history_to_disk(entry)
    _active.pop(call.id, None)
    _tasks.pop(call.id, None)


# Kept for back-compat if anyone external imports it; the inline path above
# is the canonical one.
def _dump_response(call: LlmCall, raw: str) -> str | None:
    try:
        _DUMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.fromtimestamp(call.started_at or time.time()).strftime("%Y%m%d-%H%M%S")
        filename = f"{ts}-{call.kind}-{call.id[:8]}.txt"
        path = _DUMP_DIR / filename
        path.write_text(raw, encoding="utf-8")
        return filename
    except OSError as e:
        log.warning("Failed to dump LLM response for call %s: %s", call.id, e)
        return None


def set_request(call: LlmCall, body: dict) -> None:
    """Persist the request body (messages, samplers, grammar, etc) sent to
    llama-server, for inspection from the Activity view.

    Pre-computes the filename synchronously so callers that log the path
    immediately (before the executor finishes writing) get a real name
    instead of None. The actual file write is offloaded to a thread."""
    started = call.started_at or time.time()
    ts = datetime.fromtimestamp(started).strftime("%Y%m%d-%H%M%S")
    filename = f"{ts}-{call.kind}-{call.id[:8]}.json"
    call.request_file = filename

    def _do_save():
        try:
            _REQUEST_DIR.mkdir(parents=True, exist_ok=True)
            path = _REQUEST_DIR / filename
            path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            log.warning("Failed to dump LLM request for call %s: %s", call.id, e)

    asyncio.get_event_loop().run_in_executor(None, _do_save)


def snapshot() -> dict:
    _load_history_from_disk()
    return {
        "active": [asdict(c) for c in _active.values()],
        "history": list(_history),
    }
# Load history on import
_load_history_from_disk()
