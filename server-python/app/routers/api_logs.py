"""API log routes."""
from __future__ import annotations

import json

from fastapi import APIRouter

from app.database import get_db

router = APIRouter()


@router.get("/")
async def get_api_logs(session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id, timestamp, type, model, messages, params, status, response, error, duration_ms "
        "FROM api_logs WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    return [
        {
            "id": r[0], "timestamp": r[1], "type": r[2], "model": r[3],
            "messages": json.loads(r[4]) if r[4] else [],
            "params": json.loads(r[5]) if r[5] else {},
            "status": r[6],
            "response": json.loads(r[7]) if r[7] else None,
            "error": r[8], "durationMs": r[9],
        }
        for r in rows
    ]
