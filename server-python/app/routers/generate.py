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
from app.services.prompts import build_messages
from app.services.meta_analysis import run_meta_analysis

log = logging.getLogger("pendrift.generate")
router = APIRouter()

# In-memory job tracking
_jobs: dict[str, dict] = {}
_meta_status: dict[str, dict] = {}


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
        session_row = await db.execute_fetchall("SELECT settings_preset_id, template_id, last_meta_after_chunk_index FROM sessions WHERE id = ?", (session_id,))
        preset_id = session_row[0][0]
        template_id = session_row[0][1]
        last_meta_idx = session_row[0][2]

        from app.config import DATA_DIR
        settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
        template = json.loads((DATA_DIR / "presets" / "templates" / f"{template_id}.json").read_text(encoding="utf-8"))

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

        session_row = await db.execute_fetchall("SELECT settings_preset_id, template_id FROM sessions WHERE id = ?", (session_id,))
        preset_id, template_id = session_row[0]

        from app.config import DATA_DIR
        settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
        template = json.loads((DATA_DIR / "presets" / "templates" / f"{template_id}.json").read_text(encoding="utf-8"))

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


# ── SSE Streaming generation ────────────────────────────

@router.post("/generate-stream")
async def generate_stream(session_id: str, body: dict):
    """Stream narrative generation via SSE.

    The client receives events:
      thinking_start → thinking_token* → thinking_done
      → type_resolved → narrative_start → narrative_token* → narrative_done
      → suggestions → done

    The frontend can show:
      1. A thinking indicator with live thinking text (collapsible)
      2. The narrative appearing token-by-token
      3. Suggestion buttons when they arrive
    """
    from app.services.llm_stream import stream_narrative

    directive = body.get("directive")
    chapter_id = body.get("chapterId")
    if not directive:
        raise HTTPException(400, "directive is required")

    db = await get_db()
    session_row = await db.execute_fetchall(
        "SELECT settings_preset_id, template_id, last_meta_after_chunk_index FROM sessions WHERE id = ?", (session_id,)
    )
    if not session_row:
        raise HTTPException(404, "Session not found")

    preset_id, template_id, last_meta_idx = session_row[0]
    from app.config import DATA_DIR
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{preset_id}.json").read_text(encoding="utf-8"))
    template = json.loads((DATA_DIR / "presets" / "templates" / f"{template_id}.json").read_text(encoding="utf-8"))

    chunk_rows = await db.execute_fetchall(
        'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
        (chapter_id,),
    )
    chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]

    char_rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?", (session_id,)
    )
    characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

    fact_rows = await db.execute_fetchall("SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,))
    facts = [r[0] for r in fact_rows]

    messages = build_messages(
        settings=settings, characters=characters, template=template,
        chunks=chunks, directive=directive, important_facts=facts,
        last_meta_after_chunk_index=last_meta_idx,
    )

    think_budget = settings.get("thinkingTokens", 1500)
    narrative_budget = settings.get("narrativeTokens", 500)
    suggestion_budget = settings.get("suggestionTokens", 200)

    async def event_stream():
        async for event in stream_narrative(
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
        ):
            payload = {"phase": event["phase"], "content": event["content"]}
            if "data" in event:
                payload["data"] = event["data"]
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
