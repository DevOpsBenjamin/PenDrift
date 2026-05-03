"""Chapter routes — list, get with chunks, finalize, title management."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.services import job_manager
from app.services.job_manager import Job
from app.services.meta_analysis import run_meta_analysis
from app.services.title_generator import generate_chapter_title

router = APIRouter()


@router.get("")
async def list_chapters(session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        'SELECT id, title, "order", finalized, created_at FROM chapters WHERE session_id = ? ORDER BY "order"',
        (session_id,),
    )
    return [{"id": r[0], "title": r[1], "order": r[2], "finalized": bool(r[3]), "createdAt": r[4]} for r in rows]


@router.get("/{chapter_id}")
async def get_chapter(session_id: str, chapter_id: str):
    db = await get_db()
    ch = await db.execute_fetchall(
        'SELECT id, title, "order", finalized, created_at FROM chapters WHERE id = ? AND session_id = ?',
        (chapter_id, session_id),
    )
    if not ch:
        raise HTTPException(404, "Chapter not found")
    r = ch[0]

    chunk_rows = await db.execute_fetchall(
        'SELECT id, session_id, chapter_id, "order", active_version, versions, is_key_moment, image_prompt, image_path, audio_path '
        'FROM chunks WHERE chapter_id = ? ORDER BY "order"',
        (chapter_id,),
    )
    chunks = []
    for c in chunk_rows:
        chunks.append({
            "id": c[0], "sessionId": c[1], "chapterId": c[2], "order": c[3],
            "activeVersion": c[4], "versions": json.loads(c[5]),
            "isKeyMoment": bool(c[6]), "imagePrompt": c[7], "imagePath": c[8], "audioPath": c[9],
        })

    return {"id": r[0], "title": r[1], "order": r[2], "finalized": bool(r[3]), "createdAt": r[4], "chunks": chunks}


@router.post("/finalize")
async def finalize_chapter(session_id: str, body: dict):
    chapter_id = body.get("chapterId")
    if not chapter_id:
        raise HTTPException(400, "chapterId is required")

    db = await get_db()
    ch = await db.execute_fetchall(
        'SELECT id, title, "order", finalized FROM chapters WHERE id = ? AND session_id = ?',
        (chapter_id, session_id),
    )
    if not ch:
        raise HTTPException(404, "Chapter not found")
    if ch[0][3]:
        raise HTTPException(400, "Chapter already finalized")

    chapter_order = ch[0][2]

    # Load settings
    session_row = await db.execute_fetchall("SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,))
    from app.config import DATA_DIR
    from app.routers.presets import find_default_preset_id
    raw_preset_id = session_row[0][0] if session_row else None
    eff_id = raw_preset_id if (raw_preset_id and raw_preset_id != "default") else find_default_preset_id()
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{eff_id}.json").read_text(encoding="utf-8"))

    # Load chunks
    chunk_rows = await db.execute_fetchall(
        'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
        (chapter_id,),
    )
    chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]

    # Run meta + title gen as a single job so the toast bar can show one
    # entry that progresses through both LLM calls. The job survives client
    # disconnect — chapter finalization always lands on disk.
    async def _runner(j: Job):
        if chunks:
            interval = settings.get("chunkUpdateInterval", 5)
            j.emit({"type": "phase", "name": "meta"})
            await run_meta_analysis(session_id, chunks[-interval:], settings, job=j)
            await db.execute("UPDATE sessions SET last_meta_after_chunk_index = NULL WHERE id = ?", (session_id,))
            await db.commit()
        j.emit({"type": "phase", "name": "title"})
        title_text = await generate_chapter_title(session_id, chunks, settings, chapter_order, job=j)
        j.set_result({"title": title_text})

    job = await job_manager.run_and_wait(
        kind="finalize-chapter",
        label=f"Finalize chapter · {chapter_id[:8]}",
        session_id=session_id,
        runner=_runner,
    )
    if job.status == "error":
        raise HTTPException(502, f"Finalization failed: {job.error}")
    if job.status == "cancelled":
        raise HTTPException(499, "Finalization cancelled")
    title = (job.result or {}).get("title") or f"Chapter {chapter_order + 1}"

    # Finalize
    await db.execute("UPDATE chapters SET finalized = 1, title = ? WHERE id = ?", (title, chapter_id))

    # Create next chapter
    now = datetime.now(timezone.utc).isoformat()
    count = await db.execute_fetchall("SELECT COUNT(*) FROM chapters WHERE session_id = ?", (session_id,))
    new_order = count[0][0]
    new_id = str(uuid4())

    await db.execute(
        'INSERT INTO chapters (id, session_id, title, "order", finalized, created_at) VALUES (?,?,?,?,?,?)',
        (new_id, session_id, f"Chapter {new_order + 1}", new_order, 0, now),
    )
    await db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    await db.commit()

    return {
        "finalizedChapter": {"id": chapter_id, "title": title, "order": chapter_order, "finalized": True},
        "newChapter": {"id": new_id, "title": f"Chapter {new_order + 1}", "order": new_order, "finalized": False, "createdAt": now},
    }


@router.post("/{chapter_id}/regen-title")
async def regen_title(session_id: str, chapter_id: str):
    db = await get_db()
    ch = await db.execute_fetchall(
        'SELECT "order" FROM chapters WHERE id = ? AND session_id = ?', (chapter_id, session_id)
    )
    if not ch:
        raise HTTPException(404, "Chapter not found")

    session_row = await db.execute_fetchall("SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,))
    from app.config import DATA_DIR
    from app.routers.presets import find_default_preset_id
    raw_preset_id = session_row[0][0] if session_row else None
    eff_id = raw_preset_id if (raw_preset_id and raw_preset_id != "default") else find_default_preset_id()
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{eff_id}.json").read_text(encoding="utf-8"))

    chunk_rows = await db.execute_fetchall(
        'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
        (chapter_id,),
    )
    chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]

    async def _runner(j: Job):
        title_text = await generate_chapter_title(session_id, chunks, settings, ch[0][0], job=j)
        j.set_result({"title": title_text})

    job = await job_manager.run_and_wait(
        kind="title",
        label=f"Regen title · {chapter_id[:8]}",
        session_id=session_id,
        runner=_runner,
    )
    if job.status == "error":
        raise HTTPException(502, f"Title generation failed: {job.error}")
    if job.status == "cancelled":
        raise HTTPException(499, "Title generation cancelled")
    title = (job.result or {}).get("title") or f"Chapter {ch[0][0] + 1}"
    await db.execute("UPDATE chapters SET title = ? WHERE id = ?", (title, chapter_id))
    await db.commit()

    return {"id": chapter_id, "title": title}


@router.put("/{chapter_id}")
async def update_chapter(session_id: str, chapter_id: str, body: dict):
    title = body.get("title")
    if not title:
        raise HTTPException(400, "title is required")

    db = await get_db()
    await db.execute("UPDATE chapters SET title = ? WHERE id = ? AND session_id = ?", (title, chapter_id, session_id))
    await db.commit()

    ch = await db.execute_fetchall(
        'SELECT id, title, "order", finalized, created_at FROM chapters WHERE id = ?', (chapter_id,)
    )
    if not ch:
        raise HTTPException(404, "Chapter not found")
    r = ch[0]
    return {"id": r[0], "title": r[1], "order": r[2], "finalized": bool(r[3]), "createdAt": r[4]}
