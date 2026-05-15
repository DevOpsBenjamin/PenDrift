"""Session CRUD routes."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.services import job_manager, template_store
from app.services.job_manager import Job
from app.services.meta_analysis import apply_initial_meta_to_session

log = logging.getLogger("pendrift.sessions")

router = APIRouter()


def _resolve(text: str | None, variables: dict) -> str | None:
    if not text or not variables:
        return text
    return re.sub(r"\{\{(\w+)\}\}", lambda m: variables.get(m.group(1), m.group(0)), text)


async def _chapter_chunk_counts(db, session_id: str) -> dict:
    """Return {chapter_id: chunk_count} for every chapter in the session, in
    a single query. Used to enrich the chapters response so the frontend can
    decide whether to show 'Finish Session' (only safe when the trailing
    chapter is empty or finalized)."""
    rows = await db.execute_fetchall(
        "SELECT chapter_id, COUNT(*) FROM chunks WHERE session_id = ? GROUP BY chapter_id",
        (session_id,),
    )
    return {r[0]: r[1] for r in rows}


@router.get("")
async def list_sessions():
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id, title, template_id, settings_preset_id, cover_image, created_at, updated_at, last_meta_after_chunk_index, template_version, finished_at, initial_meta_status FROM sessions ORDER BY updated_at DESC"
    )
    sessions = []
    for r in rows:
        sid = r[0]
        chapters = await db.execute_fetchall(
            'SELECT id, title, "order", finalized, created_at FROM chapters WHERE session_id = ? ORDER BY "order"', (sid,)
        )
        counts = await _chapter_chunk_counts(db, sid)
        sessions.append({
            "id": sid, "title": r[1], "templateId": r[2], "settingsPresetId": r[3],
            "coverImage": r[4], "createdAt": r[5], "updatedAt": r[6], "lastMetaAfterChunkIndex": r[7],
            "templateVersion": r[8], "finishedAt": r[9],
            "initialMetaStatus": r[10] or "done",
            "chapters": [{"id": c[0], "title": c[1], "order": c[2], "finalized": bool(c[3]), "createdAt": c[4], "chunkCount": counts.get(c[0], 0)} for c in chapters],
        })
    return sessions


@router.post("", status_code=201)
async def create_session(body: dict):
    """Create a session immediately and return — the initial meta call runs
    as a background job afterward. The session is usable right away with
    legacy-seeded characters (just initialState); the structured fields fill
    in once the background job completes. Status flow:
        pending → running → done | failed
    """
    template_id = body.get("templateId")
    if not template_id:
        raise HTTPException(400, "templateId is required")

    template = template_store.load_current(template_id)
    if template is None:
        raise HTTPException(404, f"Template '{template_id}' not found")

    snapshot_version = template_store.current_version(template_id)
    variables = template.get("variables", {})

    session_id = str(uuid4())
    chapter_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()

    from app.routers.presets import find_default_preset_id
    settings_preset_id = body.get("settingsPresetId") or find_default_preset_id()

    # Insert session in 'pending' state — initial meta hasn't run yet.
    await db.execute(
        """INSERT INTO sessions (
            id, title, template_id, template_version, settings_preset_id,
            created_at, updated_at, pending_milestones, achieved_milestones,
            initial_meta_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            session_id,
            body.get("title") or template.get("name", "Untitled"),
            template_id, snapshot_version, settings_preset_id,
            now, now, "[]", "[]",
            "pending",
        ),
    )

    await db.execute(
        'INSERT INTO chapters (id, session_id, title, "order", finalized, created_at) VALUES (?,?,?,?,?,?)',
        (chapter_id, session_id, "Chapter 1", 0, 0, now),
    )

    # Seed characters with legacy fallback (just initialState). The background
    # job will UPDATE these rows in place once initial meta completes,
    # populating identity / voice / appearance / backstory / masked_intents.
    for char in template.get("characters", []):
        name = _resolve(char.get("name", ""), variables)
        if not name:
            continue
        state = _resolve(char.get("initialState", ""), variables) or ""
        await db.execute(
            """INSERT INTO characters (
                session_id, name, current_state, traits, key_events, last_updated
            ) VALUES (?,?,?,?,?,?)""",
            (session_id, name, state, "[]", "[]", now),
        )

    await db.commit()

    # Spawn the background initial-meta job. It runs as a job_manager job so
    # it shows up in the toast bar / jobs header automatically. If the settings
    # preset can't be loaded, mark the session as failed and skip the job.
    from app.config import DATA_DIR
    settings: dict | None = None
    try:
        settings_path = DATA_DIR / "presets" / "settings" / f"{settings_preset_id}.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Could not load settings preset %s — initial meta skipped: %s", settings_preset_id, e)
        await db.execute(
            "UPDATE sessions SET initial_meta_status = 'failed' WHERE id = ?",
            (session_id,),
        )
        await db.commit()

    if settings is not None:
        async def _runner(j: Job):
            result = await apply_initial_meta_to_session(
                session_id, template, settings, job=j,
            )
            j.set_result({
                "ok": result.get("ok", False),
                "applied": result.get("applied", False),
                "pendingMilestones": result.get("pendingMilestones") or [],
                "importantFacts": result.get("importantFacts") or [],
                "consistencyFlags": result.get("consistencyFlags") or [],
            })

        job_manager.create_job(
            kind="meta_initial",
            label=f"Setting up characters · {body.get('title') or template.get('name', 'Untitled')}",
            session_id=session_id,
            runner=_runner,
        )

    return {
        "id": session_id,
        "title": body.get("title") or template.get("name", "Untitled"),
        "templateId": template_id, "templateVersion": snapshot_version,
        "settingsPresetId": settings_preset_id,
        "chapters": [{"id": chapter_id, "title": "Chapter 1", "order": 0, "finalized": False, "createdAt": now}],
        "coverImage": None, "createdAt": now, "updatedAt": now,
        "initialMetaStatus": "pending" if settings is not None else "failed",
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT id, title, template_id, settings_preset_id, cover_image, created_at, updated_at, last_meta_after_chunk_index, template_version, finished_at, initial_meta_status FROM sessions WHERE id = ?",
        (session_id,),
    )
    if not row:
        raise HTTPException(404, "Session not found")
    r = row[0]
    chapters = await db.execute_fetchall(
        'SELECT id, title, "order", finalized, created_at FROM chapters WHERE session_id = ? ORDER BY "order"', (session_id,)
    )
    counts = await _chapter_chunk_counts(db, session_id)
    return {
        "id": r[0], "title": r[1], "templateId": r[2], "settingsPresetId": r[3],
        "coverImage": r[4], "createdAt": r[5], "updatedAt": r[6], "lastMetaAfterChunkIndex": r[7],
        "templateVersion": r[8], "finishedAt": r[9],
        "initialMetaStatus": r[10] or "done",
        "chapters": [{"id": c[0], "title": c[1], "order": c[2], "finalized": bool(c[3]), "createdAt": c[4], "chunkCount": counts.get(c[0], 0)} for c in chapters],
    }


@router.put("/{session_id}")
async def update_session(session_id: str, body: dict):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    updates = []
    params = []
    for key, col in [("title", "title"), ("settingsPresetId", "settings_preset_id")]:
        if key in body:
            updates.append(f"{col} = ?")
            params.append(body[key])
    updates.append("updated_at = ?")
    params.append(now)
    params.append(session_id)

    await db.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params)
    await db.commit()
    return await get_session(session_id)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    db = await get_db()
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()
    return {"ok": True}


@router.post("/{session_id}/finish/validate")
async def validate_finish(session_id: str):
    """Lock the session — sets `finished_at`. The currently-active version of
    every chunk becomes THE version (the frontend hides the version selector
    in finished mode, and version-switching is rejected on the backend).
    Generation is also blocked. Use POST /finish/reopen to undo."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT finished_at FROM sessions WHERE id = ?", (session_id,)
    )
    if not row:
        raise HTTPException(404, "Session not found")
    if row[0][0] is not None:
        raise HTTPException(400, "Session already finished")
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET finished_at = ?, updated_at = ? WHERE id = ?",
        (now, now, session_id),
    )
    await db.commit()
    return await get_session(session_id)


@router.post("/{session_id}/finish/reopen")
async def reopen_finished(session_id: str):
    """Unlock a finished session — clears `finished_at`. Generation and version
    switching become available again. The epilogue chunk stays in place; the
    user can delete or regenerate it manually if they want."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT finished_at FROM sessions WHERE id = ?", (session_id,)
    )
    if not row:
        raise HTTPException(404, "Session not found")
    if row[0][0] is None:
        raise HTTPException(400, "Session is not finished")
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET finished_at = NULL, updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    await db.commit()
    return await get_session(session_id)


@router.put("/{session_id}/template-version")
async def set_template_version(session_id: str, body: dict):
    """Pin this session to a specific template version. Pass {"version": null}
    to unpin (sessions without a pinned version always use the template's
    currentVersion)."""
    version = body.get("version")
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT template_id FROM sessions WHERE id = ?", (session_id,)
    )
    if not row:
        raise HTTPException(404, "Session not found")
    template_id = row[0][0]

    if version is not None:
        if template_store.load_version(template_id, version) is None:
            raise HTTPException(404, f"Version '{version}' not found for template '{template_id}'")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET template_version = ?, updated_at = ? WHERE id = ?",
        (version, now, session_id),
    )
    await db.commit()
    return await get_session(session_id)
