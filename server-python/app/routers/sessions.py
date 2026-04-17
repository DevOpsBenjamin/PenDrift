"""Session CRUD routes."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.config import TEMPLATES_DIR

router = APIRouter()


def _resolve(text: str | None, variables: dict) -> str | None:
    if not text or not variables:
        return text
    return re.sub(r"\{\{(\w+)\}\}", lambda m: variables.get(m.group(1), m.group(0)), text)


@router.get("/")
async def list_sessions():
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id, title, template_id, settings_preset_id, cover_image, created_at, updated_at, last_meta_after_chunk_index FROM sessions ORDER BY updated_at DESC"
    )
    sessions = []
    for r in rows:
        sid = r[0]
        chapters = await db.execute_fetchall(
            'SELECT id, title, "order", finalized, created_at FROM chapters WHERE session_id = ? ORDER BY "order"', (sid,)
        )
        sessions.append({
            "id": sid, "title": r[1], "templateId": r[2], "settingsPresetId": r[3],
            "coverImage": r[4], "createdAt": r[5], "updatedAt": r[6], "lastMetaAfterChunkIndex": r[7],
            "chapters": [{"id": c[0], "title": c[1], "order": c[2], "finalized": bool(c[3]), "createdAt": c[4]} for c in chapters],
        })
    return sessions


@router.post("/", status_code=201)
async def create_session(body: dict):
    template_id = body.get("templateId")
    if not template_id:
        raise HTTPException(400, "templateId is required")

    template_path = TEMPLATES_DIR / f"{template_id}.json"
    if not template_path.is_file():
        # Check data dir
        from app.config import DATA_DIR
        template_path = DATA_DIR / "presets" / "templates" / f"{template_id}.json"
        if not template_path.is_file():
            raise HTTPException(404, f"Template '{template_id}' not found")

    template = json.loads(template_path.read_text(encoding="utf-8"))
    variables = template.get("variables", {})

    session_id = str(uuid4())
    chapter_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()

    await db.execute(
        "INSERT INTO sessions (id, title, template_id, settings_preset_id, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (session_id, body.get("title") or template.get("name", "Untitled"), template_id,
         body.get("settingsPresetId", "default"), now, now),
    )

    await db.execute(
        'INSERT INTO chapters (id, session_id, title, "order", finalized, created_at) VALUES (?,?,?,?,?,?)',
        (chapter_id, session_id, "Chapter 1", 0, 0, now),
    )

    # Initialize characters from template
    for char in template.get("characters", []):
        name = _resolve(char.get("name", ""), variables)
        state = _resolve(char.get("initialState", ""), variables)
        await db.execute(
            "INSERT INTO characters (session_id, name, current_state, traits, key_events, last_updated) VALUES (?,?,?,?,?,?)",
            (session_id, name, state, "[]", "[]", now),
        )

    await db.commit()

    return {
        "id": session_id, "title": body.get("title") or template.get("name", "Untitled"),
        "templateId": template_id, "settingsPresetId": body.get("settingsPresetId", "default"),
        "chapters": [{"id": chapter_id, "title": "Chapter 1", "order": 0, "finalized": False, "createdAt": now}],
        "coverImage": None, "createdAt": now, "updatedAt": now,
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT id, title, template_id, settings_preset_id, cover_image, created_at, updated_at, last_meta_after_chunk_index FROM sessions WHERE id = ?",
        (session_id,),
    )
    if not row:
        raise HTTPException(404, "Session not found")
    r = row[0]
    chapters = await db.execute_fetchall(
        'SELECT id, title, "order", finalized, created_at FROM chapters WHERE session_id = ? ORDER BY "order"', (session_id,)
    )
    return {
        "id": r[0], "title": r[1], "templateId": r[2], "settingsPresetId": r[3],
        "coverImage": r[4], "createdAt": r[5], "updatedAt": r[6], "lastMetaAfterChunkIndex": r[7],
        "chapters": [{"id": c[0], "title": c[1], "order": c[2], "finalized": bool(c[3]), "createdAt": c[4]} for c in chapters],
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
