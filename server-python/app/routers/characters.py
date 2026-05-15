"""Character and facts management routes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.services import job_manager
from app.services.job_manager import Job
from app.services.meta_analysis import run_meta_analysis

router = APIRouter()


_CHAR_COLUMNS = (
    "name, current_state, traits, key_events, identity, voice, appearance, "
    "backstory, backstory_additions, masked_intents, last_updated"
)


def _row_to_character(r) -> dict:
    return {
        "name": r[0],
        "currentState": r[1],
        "traits": json.loads(r[2]),
        "keyEvents": json.loads(r[3]),
        "identity": r[4] or "",
        "voice": r[5] or "",
        "appearance": r[6] or "",
        "backstory": r[7] or "",
        "backstoryAdditions": json.loads(r[8]) if r[8] else [],
        "maskedIntents": json.loads(r[9]) if r[9] else [],
        "lastUpdated": r[10],
    }


@router.get("")
async def list_characters(session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        f"SELECT {_CHAR_COLUMNS} FROM characters WHERE session_id = ?",
        (session_id,),
    )
    return [_row_to_character(r) for r in rows]


@router.post("")
async def add_character(session_id: str, body: dict):
    name = body.get("name")
    if not name:
        raise HTTPException(400, "Character name is required")

    db = await get_db()
    existing = await db.execute_fetchall(
        "SELECT 1 FROM characters WHERE session_id = ? AND name = ?", (session_id, name)
    )
    if existing:
        raise HTTPException(400, "Character already exists")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO characters (
            session_id, name, current_state, traits, key_events,
            identity, voice, appearance, backstory, backstory_additions,
            masked_intents, last_updated
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            session_id, name, body.get("currentState", ""),
            json.dumps(body.get("traits", [])),
            json.dumps(body.get("keyEvents", [])),
            body.get("identity", "") or "",
            body.get("voice", "") or "",
            body.get("appearance", "") or "",
            body.get("backstory", "") or "",
            json.dumps(body.get("backstoryAdditions", []) or []),
            json.dumps(body.get("maskedIntents", []) or []),
            now,
        ),
    )
    await db.commit()
    row = await db.execute_fetchall(
        f"SELECT {_CHAR_COLUMNS} FROM characters WHERE session_id = ? AND name = ?",
        (session_id, name),
    )
    return _row_to_character(row[0])


@router.put("/{char_name}")
async def update_character(session_id: str, char_name: str, body: dict):
    db = await get_db()
    existing = await db.execute_fetchall(
        "SELECT name FROM characters WHERE session_id = ? AND name = ?", (session_id, char_name)
    )
    if not existing:
        raise HTTPException(404, "Character not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = ["last_updated = ?"]
    params: list = [now]

    field_map = [
        ("currentState", "current_state", None),
        ("identity", "identity", None),
        ("voice", "voice", None),
        ("appearance", "appearance", None),
        ("backstory", "backstory", None),
        ("traits", "traits", "json"),
        ("keyEvents", "key_events", "json"),
        ("backstoryAdditions", "backstory_additions", "json"),
        ("maskedIntents", "masked_intents", "json"),
    ]
    for body_key, col, transform in field_map:
        if body_key in body:
            updates.append(f"{col} = ?")
            value = body[body_key]
            params.append(json.dumps(value) if transform == "json" else (value or ""))

    params.extend([session_id, char_name])

    await db.execute(f"UPDATE characters SET {', '.join(updates)} WHERE session_id = ? AND name = ?", params)
    await db.commit()

    row = await db.execute_fetchall(
        f"SELECT {_CHAR_COLUMNS} FROM characters WHERE session_id = ? AND name = ?",
        (session_id, char_name),
    )
    return _row_to_character(row[0])


@router.post("/update")
async def trigger_meta(session_id: str, body: dict):
    chapter_id = body.get("chapterId")
    db = await get_db()

    session_row = await db.execute_fetchall("SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,))
    if not session_row:
        raise HTTPException(404, "Session not found")

    from app.config import DATA_DIR
    from app.routers.presets import find_default_preset_id
    raw_preset_id = session_row[0][0]
    eff_id = raw_preset_id if (raw_preset_id and raw_preset_id != "default") else find_default_preset_id()
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{eff_id}.json").read_text(encoding="utf-8"))

    chunks = []
    if chapter_id:
        chunk_rows = await db.execute_fetchall(
            'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
            (chapter_id,),
        )
        chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]

    interval = settings.get("chunkUpdateInterval", 10)
    recent = chunks[-interval:]

    async def _runner(j: Job):
        result = await run_meta_analysis(session_id, recent, settings, job=j)
        j.set_result(result)

    job = await job_manager.run_and_wait(
        kind="meta",
        label=f"Meta-analysis · {len(recent)} chunks",
        session_id=session_id,
        runner=_runner,
    )
    if job.status == "cancelled":
        raise HTTPException(499, "Meta-analysis cancelled")
    if job.status == "error":
        raise HTTPException(502, f"Meta-analysis failed: {job.error}")
    return job.result


@router.post("/consolidate")
async def consolidate(session_id: str, body: dict | None = None):
    """Run a cleanup-mode meta call to consolidate character sheets and facts.

    Internally this is `run_meta_analysis` with a director-note hint that
    triggers the cleanup-mode branch of meta.md. The prompt's precision rules
    are still in effect — the model decides what to merge / drop, the hint
    just tells it to be aggressive about consolidation.

    Body (optional): { "note": "<director's free-text cleanup hint>" }
    """
    db = await get_db()

    session_row = await db.execute_fetchall(
        "SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,)
    )
    if not session_row:
        raise HTTPException(404, "Session not found")

    from app.config import DATA_DIR
    from app.routers.presets import find_default_preset_id
    raw_preset_id = session_row[0][0]
    eff_id = raw_preset_id if (raw_preset_id and raw_preset_id != "default") else find_default_preset_id()
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{eff_id}.json").read_text(encoding="utf-8"))

    director_note = (body or {}).get("note") or (
        "Cleanup pass — review character sheets and facts for redundancy. Merge near-duplicate "
        "key events, drop traits that restate identity, tighten currentState, drop facts that are "
        "obvious from character sheets, and re-evaluate any milestones that no longer fit."
    )

    interval = settings.get("chunkUpdateInterval", 10)
    chunk_rows = await db.execute_fetchall(
        '''SELECT c.id, c.chapter_id, c."order", c.active_version, c.versions
           FROM chunks c
           JOIN chapters ch ON c.chapter_id = ch.id
           WHERE c.session_id = ?
           ORDER BY ch."order" DESC, c."order" DESC
           LIMIT ?''',
        (session_id, interval),
    )
    recent = [
        {"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]}
        for r in reversed(chunk_rows)
    ]

    async def _runner(j: Job):
        result = await run_meta_analysis(
            session_id, recent, settings, job=j, director_note=director_note,
        )
        j.set_result(result)

    job = await job_manager.run_and_wait(
        kind="consolidate",
        label="Consolidate (cleanup-mode meta)",
        session_id=session_id,
        runner=_runner,
    )
    if job.status == "cancelled":
        raise HTTPException(499, "Consolidate cancelled")
    if job.status == "error":
        raise HTTPException(502, f"Consolidate failed: {job.error}")
    return job.result


@router.get("/meta-history")
async def meta_history(session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT timestamp, chunk_range, status, error, result, raw_response FROM meta_history WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    return [
        {"timestamp": r[0], "chunkRange": json.loads(r[1]), "status": r[2],
         "error": r[3], "result": json.loads(r[4]) if r[4] else None, "rawResponse": r[5]}
        for r in rows
    ]
