"""Narrative generation routes — async job-based."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from fastapi.responses import StreamingResponse

from app.database import get_db
from app.services.llm import generate_narrative
from app.services.llm_stream import stream_narrative, stream_query
from app.services.prompts import build_messages, build_query_messages
from app.services.meta_analysis import run_meta_analysis
from app.services import llm_process, template_store, job_manager
from app.services.job_manager import Job


def _load_template_for_session(template_id: str, template_version: str | None) -> dict:
    """Load the right template version for a session — pinned version if set,
    else the template's currentVersion."""
    tpl = (template_store.load_version(template_id, template_version)
           if template_version else template_store.load_current(template_id))
    if tpl is None:
        raise HTTPException(404, f"Template '{template_id}' (version {template_version or 'current'}) not found")
    return tpl

log = logging.getLogger("pendrift.generate")
router = APIRouter()

# In-memory job tracking
_jobs: dict[str, dict] = {}
_meta_status: dict[str, dict] = {}


# In-flight narrative pipelines run as `Job`s in the global queue
# (`services/job_manager.py`). Per-session uniqueness ("only one narrative
# at a time per session") is enforced via `job_manager.find_active_session_job`
# at endpoint entry rather than a local dict.


async def _prepare_generation(session_id: str, chapter_id: str, directive: str, is_key_moment: bool, job: Job | None = None):
    """Common prep: validate, run meta if needed, build messages + token budget.

    If `job` is provided, emits progress events so the frontend can show what
    the backend is doing (loading settings, running meta-analysis, etc) instead
    of looking like the model is silently thinking."""
    db = await get_db()

    session_rows = await db.execute_fetchall("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not session_rows:
        raise HTTPException(404, "Session not found")

    chapter_rows = await db.execute_fetchall(
        "SELECT id, finalized FROM chapters WHERE id = ? AND session_id = ?", (chapter_id, session_id)
    )
    if not chapter_rows:
        raise HTTPException(404, "Chapter not found")
    if chapter_rows[0][1]:
        raise HTTPException(400, "Cannot generate in a finalized chapter")

    session_row = await db.execute_fetchall(
        "SELECT settings_preset_id, template_id, last_meta_after_chunk_index, template_version FROM sessions WHERE id = ?", (session_id,)
    )
    preset_id, template_id, last_meta_idx, template_version = session_row[0]

    from app.config import DATA_DIR
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
    template = _load_template_for_session(template_id, template_version)

    chunk_rows = await db.execute_fetchall(
        'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
        (chapter_id,),
    )
    chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]
    interval = settings.get("chunkUpdateInterval", 10)

    meta_ran = False
    meta_due = bool(chunks) and (len(chunks) % interval == 0) and (last_meta_idx != len(chunks) - 1)
    if meta_due or is_key_moment:
        reason = "key_moment" if is_key_moment and not meta_due else "interval"
        log.info("Running meta-analysis (%s) before chunk %d", reason, len(chunks) + 1)
        if job is not None:
            job.emit({"type": "meta_starting", "reason": reason, "chunkCount": len(chunks)})
        _meta_status[session_id] = {"status": "updating", "result": None}
        try:
            meta_chunks = chunks[-interval:]
            result = await run_meta_analysis(session_id, meta_chunks, settings)
            _meta_status[session_id] = {"status": "done", "result": result}
            await db.execute("UPDATE sessions SET last_meta_after_chunk_index = ? WHERE id = ?", (len(chunks) - 1, session_id))
            await db.commit()
            last_meta_idx = len(chunks) - 1
            meta_ran = True
            if job is not None:
                job.emit({
                    "type": "meta_done",
                    "charactersUpdated": len(result.get("characterUpdates", [])) if isinstance(result, dict) else 0,
                    "newCharacters": len(result.get("newCharacters", [])) if isinstance(result, dict) else 0,
                    "factsCount": len(result.get("importantFacts", [])) if isinstance(result, dict) else 0,
                    "consistencyFlags": len(result.get("consistencyFlags", [])) if isinstance(result, dict) else 0,
                })
        except Exception as e:
            log.error("Meta-analysis failed: %s", e)
            _meta_status[session_id] = {"status": "failed", "result": None}
            if job is not None:
                job.emit({"type": "meta_done", "error": str(e)})

    char_rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?", (session_id,)
    )
    characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

    fact_rows = await db.execute_fetchall("SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,))
    facts = [r[0] for r in fact_rows]

    previous_chapter_chunks = None
    if not chunks:
        prev = await db.execute_fetchall(
            'SELECT id FROM chapters WHERE session_id = ? AND "order" < (SELECT "order" FROM chapters WHERE id = ?) ORDER BY "order" DESC LIMIT 1',
            (session_id, chapter_id),
        )
        if prev:
            prev_rows = await db.execute_fetchall(
                'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
                (prev[0][0],),
            )
            previous_chapter_chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in prev_rows]

    messages = build_messages(
        settings=settings, characters=characters, template=template,
        chunks=chunks, directive=directive, important_facts=facts,
        last_meta_after_chunk_index=last_meta_idx,
        previous_chapter_chunks=previous_chapter_chunks,
    )

    think_budget = settings.get("thinkingTokens", 1500)
    narrative_budget = settings.get("narrativeTokens", 500)
    suggestion_budget = settings.get("suggestionTokens", 200)
    total_budget = think_budget + narrative_budget + suggestion_budget

    return {
        "settings": settings, "messages": messages, "chunks": chunks,
        "max_tokens": total_budget, "meta_ran": meta_ran,
    }


async def _save_narrative_chunk(session_id: str, chapter_id: str, directive: str,
                                 is_key_moment: bool, llm_result: dict, order: int):
    db = await get_db()
    chunk_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    version = json.dumps([{
        "narrative": llm_result.get("narrative", ""),
        "thinking": llm_result.get("thinking"),
        "suggestions": llm_result.get("suggestions") or None,
        "stats": llm_result.get("stats", {}),
        "directive": directive,
        "from": llm_result.get("modelName", "narrative"),
        "createdAt": now,
    }])
    await db.execute(
        'INSERT INTO chunks (id, session_id, chapter_id, "order", active_version, versions, is_key_moment) VALUES (?,?,?,?,?,?,?)',
        (chunk_id, session_id, chapter_id, order, 0, version, int(is_key_moment)),
    )
    await db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    await db.commit()
    return {
        "id": chunk_id, "sessionId": session_id, "chapterId": chapter_id,
        "order": order, "activeVersion": 0,
        "versions": json.loads(version),
        "isKeyMoment": is_key_moment,
    }


async def _generation_pipeline(
    job: Job, chapter_id: str, directive: str, is_key_moment: bool,
):
    """Run the full generation in the background, emitting events to a Job
    that can be subscribed to by multiple clients (replay + live).

    Critically, this task is decoupled from the HTTP request. If clients
    disconnect, this task keeps running. Only an explicit cancel
    (via POST /api/jobs/{id}/cancel) stops it.
    """
    session_id = job.session_id
    try:
        prep = await _prepare_generation(session_id, chapter_id, directive, is_key_moment, job=job)
        settings = prep["settings"]
        job.emit({"type": "prep_done", "metaRan": prep["meta_ran"]})

        # Auto-load the model if none is running and the preset declares one
        if not llm_process.is_running():
            model_path = settings.get("modelPath")
            if not model_path:
                job.emit({"type": "error", "message": "No model is loaded and the preset has no modelPath. Load a model from the Settings page."})
                return
            from app.routers.llm_management import get_exe
            try:
                exe = get_exe()
            except HTTPException as e:
                job.emit({"type": "error", "message": e.detail})
                return
            job.emit({"type": "model_loading", "modelPath": model_path})
            try:
                await llm_process.start_server(
                    llama_server_exe=exe,
                    model_path=model_path,
                    port=settings.get("port", 8080),
                    gpu_layers=settings.get("gpuLayers", 99),
                    context_size=settings.get("contextSize", 65536),
                )
            except (RuntimeError, TimeoutError) as e:
                job.emit({"type": "error", "message": f"Failed to load model: {e}"})
                return
            job.emit({"type": "model_loaded"})

        result_for_save: dict | None = None
        async for ev in stream_narrative(
            prep["messages"],
            temperature=settings.get("temperature"),
            max_tokens=prep["max_tokens"],
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            min_p=settings.get("minP"),
            repeat_penalty=settings.get("repeatPenalty"),
            presence_penalty=settings.get("presencePenalty"),
            frequency_penalty=settings.get("frequencyPenalty"),
            seed=settings.get("seed"),
            session_id=session_id,
        ):
            if ev["type"] == "done":
                result_for_save = ev["result"]
                continue
            job.emit(ev)

        # Save chunk to DB (or skip if suggestion-only or empty)
        if not result_for_save:
            return
        if result_for_save.get("type") == "suggestion" and result_for_save.get("suggestions") and not result_for_save.get("narrative"):
            job.emit({
                "type": "done",
                "kind": "suggestion",
                "thinking": result_for_save.get("thinking", ""),
                "suggestions": result_for_save["suggestions"],
                "metaUpdatePending": prep["meta_ran"],
            })
            return
        if not result_for_save.get("narrative"):
            job.emit({"type": "error", "message": "LLM returned empty narrative"})
            return

        chunk_out = await _save_narrative_chunk(
            session_id, chapter_id, directive, is_key_moment,
            result_for_save, len(prep["chunks"])
        )
        job.emit({
            "type": "done",
            "kind": "narrative",
            "chunk": chunk_out,
            "thinking": result_for_save.get("thinking", ""),
            "suggestions": result_for_save.get("suggestions") or None,
            "metaUpdatePending": prep["meta_ran"],
        })
    except asyncio.CancelledError:
        log.info("Generation pipeline cancelled (user-requested)")
        job.emit({"type": "error", "message": "cancelled"})
        raise
    except HTTPException as e:
        job.emit({"type": "error", "message": e.detail})
    except Exception as e:
        log.exception("Generation pipeline failed")
        job.emit({"type": "error", "message": str(e)})
    # No `finally` needed: job_manager._run_job_lifecycle handles
    # status transition + finalize() + active-registry cleanup.


async def _relay_queue_to_sse(queue: asyncio.Queue):
    """Drain events from the pipeline queue and yield them as SSE frames.

    If the client disconnects, this generator is cancelled by Starlette but the
    background pipeline keeps running. The `None` sentinel marks pipeline
    completion; we exit cleanly when we see it (or when cancelled).
    """
    yield ": stream open\n\n"
    while True:
        try:
            ev = await queue.get()
        except asyncio.CancelledError:
            log.info("SSE relay cancelled (client disconnected) — pipeline continues in background")
            raise
        if ev is None:
            return
        yield _sse(ev)


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/generate/stream")
async def generate_streaming(session_id: str, body: dict):
    """Start a new streaming generation. The pipeline runs as a detached
    job in the global queue (services/job_manager.py), so client disconnects
    do NOT abort it — only POST /api/jobs/{id}/cancel can. If a narrative or
    regenerate job is already running for this session, return 409 (use GET
    /generate/stream to attach to it instead)."""
    directive = body.get("directive")
    chapter_id = body.get("chapterId")
    is_key_moment = body.get("isKeyMoment", False)
    if not directive:
        raise HTTPException(400, "directive is required")
    existing = job_manager.find_active_session_job(session_id, kinds=("narrative", "regenerate"))
    if existing is not None:
        raise HTTPException(409, "A generation is already running for this session. Use GET /generate/stream to attach.")

    job = job_manager.create_job(
        kind="narrative",
        label=f"Narrative · {directive[:60]}{'…' if len(directive) > 60 else ''}",
        session_id=session_id,
        runner=lambda j: _generation_pipeline(j, chapter_id, directive, is_key_moment),
    )

    return StreamingResponse(
        _relay_queue_to_sse(job.subscribe()),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/query/stream")
async def query_streaming(session_id: str, body: dict):
    """Ask-the-Narrator: a non-narrative analytical Q&A streamed as SSE.
    The LLM has full session context including masked intents. Body:
    {question, history?: [{question, answer}, ...]}
    """
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question is required")

    db = await get_db()
    session_row = await db.execute_fetchall(
        "SELECT settings_preset_id, template_id, template_version FROM sessions WHERE id = ?", (session_id,)
    )
    if not session_row:
        raise HTTPException(404, "Session not found")
    preset_id, template_id, template_version = session_row[0]

    from app.config import DATA_DIR
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
    template = _load_template_for_session(template_id, template_version)

    char_rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?",
        (session_id,),
    )
    characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

    fact_rows = await db.execute_fetchall(
        "SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,)
    )
    facts = [r[0] for r in fact_rows]

    # Last few chunks across all chapters for tone/state context — uses the
    # same window size as the narrative so the consultant sees the same recency.
    n_recent = max(1, int(settings.get("recentChunksCount", 5)))
    recent_rows = await db.execute_fetchall(
        'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE session_id = ? ORDER BY id DESC LIMIT ?',
        (session_id, n_recent),
    )
    recent_chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in reversed(recent_rows)]

    history = body.get("history") or []
    messages = build_query_messages(
        question=question,
        template=template,
        characters=characters,
        important_facts=facts,
        recent_chunks=recent_chunks,
        history=history,
    )

    # Auto-load model if needed (same as generate)
    async def event_source():
        yield ": stream open\n\n"
        if not llm_process.is_running():
            model_path = settings.get("modelPath")
            if not model_path:
                yield _sse({"type": "error", "message": "No model loaded and the preset has no modelPath."})
                return
            from app.routers.llm_management import get_exe
            try:
                exe = get_exe()
            except HTTPException as e:
                yield _sse({"type": "error", "message": e.detail})
                return
            yield _sse({"type": "model_loading", "modelPath": model_path})
            try:
                await llm_process.start_server(
                    llama_server_exe=exe, model_path=model_path,
                    port=settings.get("port", 8080),
                    gpu_layers=settings.get("gpuLayers", 99),
                    context_size=settings.get("contextSize", 65536),
                )
            except (RuntimeError, TimeoutError) as e:
                yield _sse({"type": "error", "message": f"Failed to load model: {e}"})
                return
            yield _sse({"type": "model_loaded"})

        async for ev in stream_query(
            messages,
            temperature=settings.get("temperature"),
            max_tokens=(settings.get("maxTokens", 4096)),
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            seed=settings.get("seed"),
            session_id=session_id,
        ):
            yield _sse(ev)

    return StreamingResponse(event_source(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/generate/stream/active")
async def stream_active_status(session_id: str):
    """Quick check: is there an in-flight narrative/regenerate job for this
    session?"""
    job = job_manager.find_active_session_job(session_id, kinds=("narrative", "regenerate"))
    if job is None:
        return {"running": False}
    return {
        "running": True,
        "jobId": job.id,
        "kind": job.kind,
        "eventCount": len(job.events),
        "done": job.is_terminal(),
    }


@router.get("/generate/stream")
async def attach_streaming(session_id: str):
    """Attach to an in-progress narrative/regenerate job for this session.
    Replays buffered events first, then forwards live ones. Returns 404 if
    no gen running."""
    job = job_manager.find_active_session_job(session_id, kinds=("narrative", "regenerate"))
    if job is None:
        raise HTTPException(404, "No generation in progress for this session")
    return StreamingResponse(
        _relay_queue_to_sse(job.subscribe()),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── Regenerate (new version of an existing chunk) ───────

async def _regen_pipeline(job: Job, chunk_id: str, directive: str):
    """Background pipeline for chunk regeneration. Builds context from chunks
    BEFORE the target, streams a new narrative, then APPENDS it as a new
    version on the existing chunk."""
    session_id = job.session_id
    try:
        db = await get_db()

        chunk_row = await db.execute_fetchall(
            'SELECT chapter_id, "order", active_version, versions FROM chunks WHERE id = ? AND session_id = ?',
            (chunk_id, session_id),
        )
        if not chunk_row:
            job.emit({"type": "error", "message": "Chunk not found"})
            return
        chapter_id, target_order, active_version_idx, versions_json = chunk_row[0]
        try:
            current_versions = json.loads(versions_json)
            current_active = current_versions[active_version_idx]
            previous_attempt = {
                "narrative": current_active.get("narrative", ""),
                "thinking": current_active.get("thinking") or "",
                "directive": current_active.get("directive") or "",
            }
        except (json.JSONDecodeError, IndexError, TypeError):
            previous_attempt = None

        session_row = await db.execute_fetchall(
            "SELECT settings_preset_id, template_id, last_meta_after_chunk_index, template_version FROM sessions WHERE id = ?",
            (session_id,),
        )
        preset_id, template_id, last_meta_idx, template_version = session_row[0]
        from app.config import DATA_DIR
        settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
        template = _load_template_for_session(template_id, template_version)

        # Context = chunks BEFORE the target one (in same chapter)
        context_rows = await db.execute_fetchall(
            'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? AND "order" < ? ORDER BY "order"',
            (chapter_id, target_order),
        )
        context_chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in context_rows]

        char_rows = await db.execute_fetchall(
            "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?",
            (session_id,),
        )
        characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

        fact_rows = await db.execute_fetchall(
            "SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,)
        )
        facts = [r[0] for r in fact_rows]

        messages = build_messages(
            settings=settings, characters=characters, template=template,
            chunks=context_chunks, directive=directive, important_facts=facts,
            last_meta_after_chunk_index=last_meta_idx,
            previous_attempt=previous_attempt,
        )

        job.emit({"type": "prep_done", "metaRan": False})

        # Auto-load if model not running (same as gen pipeline)
        if not llm_process.is_running():
            model_path = settings.get("modelPath")
            if not model_path:
                job.emit({"type": "error", "message": "No model is loaded and the preset has no modelPath."})
                return
            from app.routers.llm_management import get_exe
            try:
                exe = get_exe()
            except HTTPException as e:
                job.emit({"type": "error", "message": e.detail})
                return
            job.emit({"type": "model_loading", "modelPath": model_path})
            try:
                await llm_process.start_server(
                    llama_server_exe=exe, model_path=model_path,
                    port=settings.get("port", 8080),
                    gpu_layers=settings.get("gpuLayers", 99),
                    context_size=settings.get("contextSize", 65536),
                )
            except (RuntimeError, TimeoutError) as e:
                job.emit({"type": "error", "message": f"Failed to load model: {e}"})
                return
            job.emit({"type": "model_loaded"})

        think_budget = settings.get("thinkingTokens", 1500)
        narrative_budget = settings.get("narrativeTokens", 500)
        suggestion_budget = settings.get("suggestionTokens", 200)

        result_for_save: dict | None = None
        async for ev in stream_narrative(
            messages,
            temperature=settings.get("temperature"),
            max_tokens=think_budget + narrative_budget + suggestion_budget,
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            min_p=settings.get("minP"),
            repeat_penalty=settings.get("repeatPenalty"),
            presence_penalty=settings.get("presencePenalty"),
            frequency_penalty=settings.get("frequencyPenalty"),
            seed=settings.get("seed"),
            session_id=session_id,
        ):
            if ev["type"] == "done":
                result_for_save = ev["result"]
                continue
            job.emit(ev)

        if not result_for_save or not result_for_save.get("narrative"):
            job.emit({"type": "error", "message": "LLM returned empty narrative"})
            return

        # Append new version to the existing chunk
        now = datetime.now(timezone.utc).isoformat()
        full_chunk = await db.execute_fetchall("SELECT versions FROM chunks WHERE id = ?", (chunk_id,))
        versions = json.loads(full_chunk[0][0])
        new_version = {
            "narrative": result_for_save["narrative"],
            "thinking": result_for_save.get("thinking"),
            "suggestions": result_for_save.get("suggestions") or None,
            "stats": result_for_save.get("stats", {}),
            "directive": directive,
            "from": result_for_save.get("modelName", "regenerate"),
            "createdAt": now,
        }
        versions.append(new_version)
        new_active = len(versions) - 1
        await db.execute(
            "UPDATE chunks SET versions = ?, active_version = ? WHERE id = ?",
            (json.dumps(versions), new_active, chunk_id),
        )
        await db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        await db.commit()

        job.emit({
            "type": "done",
            "kind": "narrative",
            "chunk": {"id": chunk_id, "versions": versions, "activeVersion": new_active},
            "thinking": result_for_save.get("thinking", ""),
            "suggestions": result_for_save.get("suggestions") or None,
            "metaUpdatePending": False,
        })
    except asyncio.CancelledError:
        log.info("Regen pipeline cancelled (user-requested)")
        job.emit({"type": "error", "message": "cancelled"})
        raise
    except Exception as e:
        log.exception("Regen pipeline failed")
        job.emit({"type": "error", "message": str(e)})
    # No finally: lifecycle handled by job_manager.


@router.post("/regenerate/stream")
async def regenerate_streaming(session_id: str, body: dict):
    """Stream a regeneration of an existing chunk. Same SSE contract as
    /generate/stream — events are buffered + replayable, client disconnect
    does not abort the pipeline."""
    chunk_id = body.get("chunkId")
    new_directive = body.get("directive")
    if not chunk_id:
        raise HTTPException(400, "chunkId is required")
    existing = job_manager.find_active_session_job(session_id, kinds=("narrative", "regenerate"))
    if existing is not None:
        raise HTTPException(409, "A generation is already running for this session. Use GET /generate/stream to attach.")

    db = await get_db()
    chunk_rows = await db.execute_fetchall(
        "SELECT active_version, versions FROM chunks WHERE id = ? AND session_id = ?",
        (chunk_id, session_id),
    )
    if not chunk_rows:
        raise HTTPException(404, "Chunk not found")

    versions = json.loads(chunk_rows[0][1])
    active_ver = versions[chunk_rows[0][0]]
    directive = new_directive or active_ver.get("directive")
    if not directive:
        raise HTTPException(400, "No directive to regenerate from")

    job = job_manager.create_job(
        kind="regenerate",
        label=f"Regenerate · {directive[:60]}{'…' if len(directive) > 60 else ''}",
        session_id=session_id,
        runner=lambda j: _regen_pipeline(j, chunk_id, directive),
    )

    return StreamingResponse(
        _relay_queue_to_sse(job.subscribe()),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/generate", status_code=202)
async def generate(session_id: str, body: dict):
    directive = body.get("directive")
    chapter_id = body.get("chapterId")
    is_key_moment = body.get("isKeyMoment", False)

    if not directive:
        raise HTTPException(400, "directive is required")

    db = await get_db()

    # Validate session and chapter
    session_rows = await db.execute_fetchall("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not session_rows:
        raise HTTPException(404, "Session not found")

    chapter_rows = await db.execute_fetchall(
        "SELECT id, finalized FROM chapters WHERE id = ? AND session_id = ?", (chapter_id, session_id)
    )
    if not chapter_rows:
        raise HTTPException(404, "Chapter not found")
    if chapter_rows[0][1]:
        raise HTTPException(400, "Cannot generate in a finalized chapter")

    job_id = f"job_{int(datetime.now(timezone.utc).timestamp())}_{uuid4().hex[:8]}"
    _jobs[job_id] = {"status": "generating", "sessionId": session_id, "chapterId": chapter_id, "result": None, "error": None}

    asyncio.create_task(_run_generation(job_id, session_id, chapter_id, directive, is_key_moment))
    return {"jobId": job_id}


async def _run_generation(job_id: str, session_id: str, chapter_id: str, directive: str, is_key_moment: bool):
    try:
        db = await get_db()

        # Load settings
        session_row = await db.execute_fetchall("SELECT settings_preset_id, template_id, last_meta_after_chunk_index, template_version FROM sessions WHERE id = ?", (session_id,))
        preset_id = session_row[0][0]
        template_id = session_row[0][1]
        last_meta_idx = session_row[0][2]
        template_version = session_row[0][3]

        from app.config import DATA_DIR
        settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
        template = _load_template_for_session(template_id, template_version)

        # Load chunks for this chapter
        chunk_rows = await db.execute_fetchall(
            'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
            (chapter_id,),
        )
        chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]
        interval = settings.get("chunkUpdateInterval", 10)

        # Meta trigger
        meta_ran = False
        if chunks and len(chunks) % interval == 0 and last_meta_idx != len(chunks) - 1:
            log.info("Running meta-analysis before chunk %d", len(chunks) + 1)
            _meta_status[session_id] = {"status": "updating", "result": None}
            try:
                meta_chunks = chunks[-interval:]
                result = await run_meta_analysis(session_id, meta_chunks, settings)
                _meta_status[session_id] = {"status": "done", "result": result}
                await db.execute("UPDATE sessions SET last_meta_after_chunk_index = ? WHERE id = ?", (len(chunks) - 1, session_id))
                await db.commit()
                last_meta_idx = len(chunks) - 1
                meta_ran = True
            except Exception as e:
                log.error("Meta-analysis failed: %s", e)
                _meta_status[session_id] = {"status": "failed", "result": None}

        if is_key_moment and not meta_ran:
            log.info("Key moment triggered meta-analysis")
            _meta_status[session_id] = {"status": "updating", "result": None}
            try:
                meta_chunks = chunks[-interval:]
                result = await run_meta_analysis(session_id, meta_chunks, settings)
                _meta_status[session_id] = {"status": "done", "result": result}
                await db.execute("UPDATE sessions SET last_meta_after_chunk_index = ? WHERE id = ?", (len(chunks) - 1, session_id))
                await db.commit()
                meta_ran = True
            except Exception as e:
                log.error("Key moment meta failed: %s", e)
                _meta_status[session_id] = {"status": "failed", "result": None}

        # Reload characters and facts
        char_rows = await db.execute_fetchall(
            "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?", (session_id,)
        )
        characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

        fact_rows = await db.execute_fetchall("SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,))
        facts = [r[0] for r in fact_rows]

        # Cross-chapter context
        previous_chapter_chunks = None
        if not chunks:
            prev = await db.execute_fetchall(
                'SELECT id FROM chapters WHERE session_id = ? AND "order" < (SELECT "order" FROM chapters WHERE id = ?) ORDER BY "order" DESC LIMIT 1',
                (session_id, chapter_id),
            )
            if prev:
                prev_rows = await db.execute_fetchall(
                    'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
                    (prev[0][0],),
                )
                previous_chapter_chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in prev_rows]

        messages = build_messages(
            settings=settings, characters=characters, template=template,
            chunks=chunks, directive=directive, important_facts=facts,
            last_meta_after_chunk_index=last_meta_idx,
            previous_chapter_chunks=previous_chapter_chunks,
        )

        # Token budget from settings (defaults: 1500 think + 500 narrative + 200 suggestions)
        think_budget = settings.get("thinkingTokens", 1500)
        narrative_budget = settings.get("narrativeTokens", 500)
        suggestion_budget = settings.get("suggestionTokens", 200)
        total_budget = think_budget + narrative_budget + suggestion_budget

        llm_result = await generate_narrative(
            messages,
            temperature=settings.get("temperature"),
            max_tokens=total_budget,
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            min_p=settings.get("minP"),
            repeat_penalty=settings.get("repeatPenalty"),
            presence_penalty=settings.get("presencePenalty"),
            frequency_penalty=settings.get("frequencyPenalty"),
            seed=settings.get("seed"),
            session_id=session_id,
        )

        response_type = llm_result["type"]
        narrative = llm_result["narrative"]
        suggestions = llm_result["suggestions"]

        # If model chose suggestion mode — return suggestions without creating a chunk
        if response_type == "suggestion" and suggestions and not narrative:
            _jobs[job_id] = {
                **_jobs[job_id], "status": "done",
                "result": {
                    "type": "suggestion",
                    "thinking": llm_result.get("thinking"),
                    "suggestions": suggestions,
                    "metaUpdatePending": meta_ran,
                },
            }
            return

        if not narrative:
            _jobs[job_id] = {**_jobs[job_id], "status": "failed", "error": "LLM returned empty narrative"}
            return

        # Append chunk
        chunk_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        order = len(chunks)
        version = json.dumps([{
            "narrative": narrative,
            "thinking": llm_result.get("thinking"),
            "suggestions": suggestions if suggestions else None,
            "stats": llm_result.get("stats", {}),
            "directive": directive,
            "from": llm_result.get("modelName", "narrative"),
            "createdAt": now,
        }])

        await db.execute(
            'INSERT INTO chunks (id, session_id, chapter_id, "order", active_version, versions, is_key_moment) VALUES (?,?,?,?,?,?,?)',
            (chunk_id, session_id, chapter_id, order, 0, version, int(is_key_moment)),
        )
        await db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        await db.commit()

        chunk_out = {
            "id": chunk_id, "sessionId": session_id, "chapterId": chapter_id,
            "order": order, "activeVersion": 0,
            "versions": json.loads(version),
            "isKeyMoment": is_key_moment,
        }

        _jobs[job_id] = {
            **_jobs[job_id], "status": "done",
            "result": {
                "type": "narrative",
                "chunk": chunk_out,
                "thinking": llm_result.get("thinking"),
                "suggestions": suggestions if suggestions else None,
                "metaUpdatePending": meta_ran,
            },
        }

    except Exception as e:
        log.exception("Generation job failed")
        _jobs[job_id] = {**_jobs[job_id], "status": "failed", "error": str(e)}


@router.get("/jobs/{job_id}")
async def get_job(session_id: str, job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    # Auto-cleanup after read
    if job["status"] in ("done", "failed"):
        asyncio.get_event_loop().call_later(30, lambda: _jobs.pop(job_id, None))
    return job


@router.post("/regenerate", status_code=202)
async def regenerate(session_id: str, body: dict):
    chunk_id = body.get("chunkId")
    chapter_id = body.get("chapterId")
    new_directive = body.get("directive")

    if not chunk_id:
        raise HTTPException(400, "chunkId is required")

    db = await get_db()
    chunk_rows = await db.execute_fetchall(
        "SELECT id, chapter_id, active_version, versions FROM chunks WHERE id = ? AND session_id = ?",
        (chunk_id, session_id),
    )
    if not chunk_rows:
        raise HTTPException(404, "Chunk not found")

    r = chunk_rows[0]
    versions = json.loads(r[3])
    active_ver = versions[r[2]]
    directive = new_directive or active_ver.get("directive")
    if not directive:
        raise HTTPException(400, "No directive to regenerate from")

    job_id = f"job_{int(datetime.now(timezone.utc).timestamp())}_{uuid4().hex[:8]}"
    _jobs[job_id] = {"status": "generating", "sessionId": session_id, "chunkId": chunk_id, "result": None, "error": None}

    asyncio.create_task(_run_regen(job_id, session_id, chunk_id, r[1], directive))
    return {"jobId": job_id}


async def _run_regen(job_id: str, session_id: str, chunk_id: str, chapter_id: str, directive: str):
    try:
        db = await get_db()

        session_row = await db.execute_fetchall("SELECT settings_preset_id, template_id, template_version FROM sessions WHERE id = ?", (session_id,))
        preset_id, template_id, template_version = session_row[0]

        from app.config import DATA_DIR
        settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
        template = _load_template_for_session(template_id, template_version)

        # Get chunks BEFORE this one
        target_row = await db.execute_fetchall('SELECT "order" FROM chunks WHERE id = ?', (chunk_id,))
        target_order = target_row[0][0]

        context_rows = await db.execute_fetchall(
            'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? AND "order" < ? ORDER BY "order"',
            (chapter_id, target_order),
        )
        context_chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in context_rows]

        char_rows = await db.execute_fetchall(
            "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?", (session_id,)
        )
        characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

        fact_rows = await db.execute_fetchall("SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,))
        facts = [r[0] for r in fact_rows]

        messages = build_messages(
            settings=settings, characters=characters, template=template,
            chunks=context_chunks, directive=directive, important_facts=facts,
        )

        think_budget = settings.get("thinkingTokens", 1500)
        narrative_budget = settings.get("narrativeTokens", 500)
        suggestion_budget = settings.get("suggestionTokens", 200)

        llm_result = await generate_narrative(
            messages,
            temperature=settings.get("temperature"),
            max_tokens=think_budget + narrative_budget + suggestion_budget,
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            min_p=settings.get("minP"),
            repeat_penalty=settings.get("repeatPenalty"),
            presence_penalty=settings.get("presencePenalty"),
            frequency_penalty=settings.get("frequencyPenalty"),
            seed=settings.get("seed"),
            session_id=session_id,
        )

        narrative = llm_result["narrative"]
        if not narrative:
            _jobs[job_id] = {**_jobs[job_id], "status": "failed", "error": "LLM returned empty narrative"}
            return

        # Add new version
        now = datetime.now(timezone.utc).isoformat()
        chunk_row = await db.execute_fetchall("SELECT versions FROM chunks WHERE id = ?", (chunk_id,))
        versions = json.loads(chunk_row[0][0])
        new_version = {
            "narrative": narrative,
            "thinking": llm_result.get("thinking"),
            "stats": llm_result.get("stats", {}),
            "directive": directive,
            "from": llm_result.get("modelName", "regenerate"),
            "createdAt": now,
        }
        versions.append(new_version)
        new_active = len(versions) - 1

        await db.execute(
            "UPDATE chunks SET versions = ?, active_version = ? WHERE id = ?",
            (json.dumps(versions), new_active, chunk_id),
        )
        await db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        await db.commit()

        _jobs[job_id] = {
            **_jobs[job_id], "status": "done",
            "result": {"chunk": {"id": chunk_id, "versions": versions, "activeVersion": new_active}},
        }

    except Exception as e:
        log.exception("Regeneration job failed")
        _jobs[job_id] = {**_jobs[job_id], "status": "failed", "error": str(e)}


@router.get("/meta/status")
async def meta_status(session_id: str):
    return _meta_status.get(session_id, {"status": "idle", "result": None})


