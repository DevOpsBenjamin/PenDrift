"""Universal job endpoints: list, attach via SSE, cancel.

These work for any job kind (narrative, chub-import, meta, title, ...). The
frontend's toast bar + Activity view consume `/api/jobs` (live state via SSE
on `/api/jobs/stream`) and attach to a specific job's event stream via
`/api/jobs/{id}/stream`.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services import job_manager

router = APIRouter()
log = logging.getLogger("pendrift.jobs")


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("")
async def list_jobs():
    """All known jobs — active (queued + running) first, then recent history."""
    return {"jobs": job_manager.list_jobs()}


@router.get("/stream")
async def stream_state():
    """Long-lived SSE that pushes a `jobs_state` snapshot every time anything
    changes (creation, status transition, cancellation, completion). The first
    message is the current snapshot so the client doesn't need a separate GET.
    """
    queue = job_manager.subscribe_to_state()

    async def gen():
        try:
            yield ": jobs state stream open\n\n"
            while True:
                ev = await queue.get()
                yield _sse(ev)
        except asyncio.CancelledError:
            log.debug("jobs state subscriber disconnected")
            raise
        finally:
            job_manager.unsubscribe_from_state(queue)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/{job_id}/stream")
async def stream_job(job_id: str):
    """Attach to a specific job's event stream. Replays everything emitted so
    far, then continues live. Closes when the job is terminal.

    Safe to disconnect and reconnect — the job runs in the background and the
    next attach will replay from the start."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def gen():
        yield ": job stream open\n\n"
        async for ev in job_manager.stream_job_events(job):
            yield _sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Snapshot of a single job, including its full event log. Useful for the
    Activity detail panel without keeping an SSE open."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {**job.to_dict(), "events": job.events, "result": job.result}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a queued or running job. No-op if the job is already terminal."""
    if not job_manager.cancel_job(job_id):
        raise HTTPException(404, "Job not found or already finished")
    return {"ok": True}
