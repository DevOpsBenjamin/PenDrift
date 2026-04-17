"""Facts routes — GET/PUT for session facts."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from app.database import get_db

router = APIRouter()


@router.get("/")
async def get_facts(session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,)
    )
    return [r[0] for r in rows]


@router.put("/")
async def save_facts(session_id: str, body: dict):
    facts = body.get("facts", [])
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    await db.execute("DELETE FROM facts WHERE session_id = ?", (session_id,))
    for fact in facts:
        await db.execute(
            "INSERT INTO facts (session_id, fact, created_at) VALUES (?,?,?)",
            (session_id, fact, now),
        )
    await db.commit()
    return facts
