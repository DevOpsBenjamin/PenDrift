"""Job manager — sequential queue of background LLM operations with SSE
replay+live attach.

Every long-running LLM operation (narrative generation, regenerate, chub
import, enrich, rerun, meta-analysis run as a standalone, title generation,
ask-the-narrator query, ...) is represented as a `Job`.

Properties:
- Runs as a detached `asyncio.Task` — survives client disconnects.
- Sequential globally: only one job runs at a time. Others queue in FIFO order
  and report their position so the UI can show "queued (1 ahead)".
- Emits a stream of events. Late subscribers replay the buffer and continue
  live until the job is terminal.
- In-memory only. A Python restart wipes all jobs (running ones would be
  corrupt anyway).

Wiring: callers register a job with `create_job(kind, label, runner, ...)`,
get a `Job` back, and the registry handles queueing + execution. Inside the
runner coroutine, emit events with `job.emit(...)`. The SSE endpoint is
`/api/jobs/{id}/stream`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

log = logging.getLogger("pendrift.jobs")

# ── Configuration ───────────────────────────────────────
_MAX_HISTORY = 100  # number of finished jobs we remember for the Activity view


# ── Job model ───────────────────────────────────────────
@dataclass
class Job:
    """An in-flight or recently-finished LLM operation."""

    id: str
    kind: str                       # "narrative", "regenerate", "chub-import", ...
    label: str                      # human-readable description for the UI
    session_id: str | None = None   # set when the job belongs to a session
    status: str = "queued"          # "queued" | "running" | "done" | "cancelled" | "error"
    error: str | None = None
    result: Any = None              # whatever the runner sets via `job.set_result()`

    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    # Replay buffer of every event emitted so far. Used so a late subscriber
    # can catch up before going live.
    events: list[dict] = field(default_factory=list)
    # Live subscribers — each gets a queue. We push every emitted event into
    # all of them. None pushed at finalize signals end-of-stream.
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    # Underlying asyncio task running the runner coroutine. Held so cancel()
    # can target it. None until the job actually starts running.
    task: asyncio.Task | None = None

    # ── Event API used by the runner ─────────────────────
    def emit(self, event: dict) -> None:
        """Append an event to the buffer and broadcast to live subscribers."""
        self.events.append(event)
        for q in self._subscribers:
            q.put_nowait(event)

    def set_result(self, result: Any) -> None:
        """Stash a final payload (e.g. the imported template, the saved chunk)
        so the HTTP creator can return it, and the Activity view can show it."""
        self.result = result

    # ── Subscriber API used by the SSE endpoint ──────────
    def subscribe(self) -> asyncio.Queue:
        """Get a queue pre-loaded with every event so far. After replay, the
        queue receives live events until the job terminates (then `None`)."""
        q: asyncio.Queue = asyncio.Queue()
        for ev in self.events:
            q.put_nowait(ev)
        if self.is_terminal():
            q.put_nowait(None)
        else:
            self._subscribers.append(q)
        return q

    def is_terminal(self) -> bool:
        return self.status in ("done", "cancelled", "error")

    def _finalize(self) -> None:
        """Close all live subscriber queues. Called by the runner wrapper."""
        for q in self._subscribers:
            q.put_nowait(None)
        self._subscribers.clear()

    # ── Serialization for /api/jobs ──────────────────────
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "sessionId": self.session_id,
            "status": self.status,
            "error": self.error,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "queuePosition": _queue_position_of(self) if self.status == "queued" else None,
        }


# ── Registry state ──────────────────────────────────────
# Active jobs (queued + running) keyed by id.
_active: dict[str, Job] = {}
# FIFO order in which jobs were created — used to compute queue position.
_order: list[str] = []
# Global lock: only one job runs at a time. Acquires are FIFO in CPython
# asyncio.Lock since Python 3.10, so the queue order matches creation order.
# Lazy-init (mirrors llm.py) so module import works without a running loop.
_run_lock: asyncio.Lock | None = None


def _get_run_lock() -> asyncio.Lock:
    global _run_lock
    if _run_lock is None:
        _run_lock = asyncio.Lock()
    return _run_lock
# Recently finished jobs, for the Activity view.
_history: deque[Job] = deque(maxlen=_MAX_HISTORY)
# Listeners for cross-job state changes (used by the global jobs SSE stream).
# Each is an asyncio.Queue that receives a snapshot dict whenever any job
# changes status or position.
_state_listeners: list[asyncio.Queue] = []


def _queue_position_of(job: Job) -> int:
    """0 = running, 1 = first in line, etc. Computed on demand from `_order`."""
    pos = 0
    for jid in _order:
        j = _active.get(jid)
        if not j:
            continue
        if j is job:
            return pos
        pos += 1
    return pos


def _broadcast_state() -> None:
    """Push a fresh snapshot to every state listener. Called on every status
    or queue change so the toast bar / Activity view stay in sync without
    polling."""
    snapshot = {"type": "jobs_state", "jobs": list_jobs()}
    for q in _state_listeners:
        q.put_nowait(snapshot)


# ── Public API ──────────────────────────────────────────
def create_job(
    *,
    kind: str,
    label: str,
    runner: Callable[[Job], Awaitable[None]],
    session_id: str | None = None,
) -> Job:
    """Register a new job and schedule it. Returns the Job immediately —
    it may still be queued behind other jobs.

    `runner` is a coroutine factory that takes the Job and does the work.
    It should call `job.emit(...)` to stream events and `job.set_result(...)`
    when done. Exceptions become `status=error`. Cancellation becomes
    `status=cancelled`.
    """
    job = Job(id=str(uuid4()), kind=kind, label=label, session_id=session_id)
    _active[job.id] = job
    _order.append(job.id)
    job.task = asyncio.create_task(_run_job_lifecycle(job, runner))
    log.info("[job %s] created  kind=%s  label=%r  position=%d",
             job.id[:8], kind, label, _queue_position_of(job))
    _broadcast_state()
    return job


def get_job(job_id: str) -> Job | None:
    return _active.get(job_id) or next((j for j in _history if j.id == job_id), None)


def list_jobs() -> list[dict]:
    """All currently-tracked jobs (active first, then recent history)."""
    active = [_active[jid].to_dict() for jid in _order if jid in _active]
    historical = [j.to_dict() for j in reversed(_history)]
    return active + historical


def find_active_session_job(
    session_id: str,
    *,
    kinds: tuple[str, ...] | None = None,
) -> Job | None:
    """Return the in-flight job (queued or running) for this session, or None.

    Used by per-session "is something already running?" checks (e.g., narrative
    pipelines refuse to start a second one and tell the client to attach
    instead). If `kinds` is provided, restrict to those kinds.
    """
    for jid in _order:
        j = _active.get(jid)
        if not j or j.session_id != session_id:
            continue
        if kinds is not None and j.kind not in kinds:
            continue
        return j
    return None


def cancel_job(job_id: str) -> bool:
    """Cancel a job by ID. Works for both queued and running jobs.

    For a queued job, the task is cancelled before it acquires the lock — it
    transitions directly to `cancelled` without ever running. For a running
    job, CancelledError propagates into the runner which is responsible for
    its own cleanup (e.g., closing the SSE stream to llama-server)."""
    job = _active.get(job_id)
    if not job or not job.task or job.task.done():
        return False
    job.task.cancel()
    return True


def subscribe_to_state() -> asyncio.Queue:
    """Get a queue that receives a `jobs_state` snapshot on every change.
    The queue is pre-loaded with the current snapshot so a fresh subscriber
    immediately sees the up-to-date list."""
    q: asyncio.Queue = asyncio.Queue()
    q.put_nowait({"type": "jobs_state", "jobs": list_jobs()})
    _state_listeners.append(q)
    return q


def unsubscribe_from_state(q: asyncio.Queue) -> None:
    try:
        _state_listeners.remove(q)
    except ValueError:
        pass


# ── Lifecycle wrapper ───────────────────────────────────
async def _run_job_lifecycle(job: Job, runner: Callable[[Job], Awaitable[None]]) -> None:
    """Wait for the lock (queue), run the user-supplied runner, then finalize.

    All status transitions and broadcast logic live here so individual
    runners only worry about doing their work and emitting events.
    """
    try:
        # While queued, listeners want to see position changes — but we don't
        # actually change anything here; position is computed dynamically and
        # broadcast already happened at create time. The next broadcast comes
        # when this job (or one ahead of it) starts.

        async with _get_run_lock():
            job.status = "running"
            job.started_at = time.time()
            log.info("[job %s] running  kind=%s", job.id[:8], job.kind)
            _broadcast_state()

            await runner(job)

            job.status = "done"
            log.info("[job %s] done", job.id[:8])

    except asyncio.CancelledError:
        job.status = "cancelled"
        log.info("[job %s] cancelled", job.id[:8])
        # Don't re-raise — the wrapper task is supposed to consume the cancel
        # so the registry can clean up. Re-raising would surface a noisy
        # CancelledError on the asyncio loop.

    except Exception as e:
        job.status = "error"
        job.error = str(e)
        log.exception("[job %s] failed: %s", job.id[:8], e)

    finally:
        job.finished_at = time.time()
        # Move to history before finalizing so observers see the terminal
        # status in the snapshot.
        _active.pop(job.id, None)
        try:
            _order.remove(job.id)
        except ValueError:
            pass
        _history.appendleft(job)
        job._finalize()
        _broadcast_state()


# ── SSE replay helper ───────────────────────────────────
async def stream_job_events(job: Job) -> AsyncIterator[dict]:
    """Yield events from a job: replay the buffer, then live until done.
    Convenient wrapper used by the SSE endpoint."""
    queue = job.subscribe()
    while True:
        ev = await queue.get()
        if ev is None:
            return
        yield ev
