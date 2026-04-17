"""Chunk editing routes — version management, manual edit, delete."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.database import get_db

router = APIRouter()


@router.put("/{chunk_id}")
async def edit_chunk(session_id: str, chunk_id: str, body: dict):
    narrative = body.get("narrative")
    if not narrative:
        raise HTTPException(400, "narrative is required")

    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT versions, active_version FROM chunks WHERE id = ? AND session_id = ?",
        (chunk_id, session_id),
    )
    if not row:
        raise HTTPException(404, "Chunk not found")

    versions = json.loads(row[0][0])
    active_ver = versions[row[0][1]]
    now = datetime.now(timezone.utc).isoformat()

    versions.append({
        "narrative": narrative,
        "thinking": active_ver.get("thinking"),
        "stats": None,
        "directive": active_ver.get("directive"),
        "from": "manual edit",
        "createdAt": now,
    })
    new_active = len(versions) - 1

    await db.execute(
        "UPDATE chunks SET versions = ?, active_version = ? WHERE id = ?",
        (json.dumps(versions), new_active, chunk_id),
    )
    await db.commit()

    return {"id": chunk_id, "versions": versions, "activeVersion": new_active}


@router.delete("/{chunk_id}/version")
async def delete_version(session_id: str, chunk_id: str, body: dict):
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT versions, active_version FROM chunks WHERE id = ? AND session_id = ?",
        (chunk_id, session_id),
    )
    if not row:
        raise HTTPException(404, "Chunk not found")

    versions = json.loads(row[0][0])
    active = row[0][1]

    if len(versions) <= 1:
        await db.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
        await db.commit()
        return {"deleted": "chunk"}

    idx = body.get("versionIndex", active)
    versions.pop(idx)
    new_active = min(active, len(versions) - 1)

    await db.execute(
        "UPDATE chunks SET versions = ?, active_version = ? WHERE id = ?",
        (json.dumps(versions), new_active, chunk_id),
    )
    await db.commit()
    return {"deleted": "version", "chunk": {"id": chunk_id, "versions": versions, "activeVersion": new_active}}


@router.put("/{chunk_id}/version")
async def switch_version(session_id: str, chunk_id: str, body: dict):
    version_index = body.get("versionIndex")
    if version_index is None:
        raise HTTPException(400, "versionIndex is required")

    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT versions FROM chunks WHERE id = ? AND session_id = ?",
        (chunk_id, session_id),
    )
    if not row:
        raise HTTPException(404, "Chunk not found")

    versions = json.loads(row[0][0])
    if version_index < 0 or version_index >= len(versions):
        raise HTTPException(400, "Invalid versionIndex")

    await db.execute("UPDATE chunks SET active_version = ? WHERE id = ?", (version_index, chunk_id))
    await db.commit()
    return {"id": chunk_id, "versions": versions, "activeVersion": version_index}


@router.delete("/last")
async def delete_last_chunk(session_id: str, chapterId: str = Query(...)):
    db = await get_db()
    row = await db.execute_fetchall(
        'SELECT id FROM chunks WHERE session_id = ? AND chapter_id = ? ORDER BY "order" DESC LIMIT 1',
        (session_id, chapterId),
    )
    if not row:
        raise HTTPException(404, "No chunks to delete")

    await db.execute("DELETE FROM chunks WHERE id = ?", (row[0][0],))
    await db.commit()
    return {"deleted": row[0][0]}
