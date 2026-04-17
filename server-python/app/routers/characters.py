"""Character and facts management routes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.services.meta_analysis import run_meta_analysis
from app.services.llm import generate_completion

router = APIRouter()


@router.get("/")
async def list_characters(session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events, last_updated FROM characters WHERE session_id = ?",
        (session_id,),
    )
    return [
        {"name": r[0], "currentState": r[1], "traits": json.loads(r[2]),
         "keyEvents": json.loads(r[3]), "lastUpdated": r[4]}
        for r in rows
    ]


@router.post("/")
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
        "INSERT INTO characters (session_id, name, current_state, traits, key_events, last_updated) VALUES (?,?,?,?,?,?)",
        (session_id, name, body.get("currentState", ""),
         json.dumps(body.get("traits", [])), json.dumps(body.get("keyEvents", [])), now),
    )
    await db.commit()
    return {"name": name, "currentState": body.get("currentState", ""),
            "traits": body.get("traits", []), "keyEvents": body.get("keyEvents", []), "lastUpdated": now}


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
    params = [now]
    if "currentState" in body:
        updates.append("current_state = ?")
        params.append(body["currentState"])
    if "traits" in body:
        updates.append("traits = ?")
        params.append(json.dumps(body["traits"]))
    if "keyEvents" in body:
        updates.append("key_events = ?")
        params.append(json.dumps(body["keyEvents"]))
    params.extend([session_id, char_name])

    await db.execute(f"UPDATE characters SET {', '.join(updates)} WHERE session_id = ? AND name = ?", params)
    await db.commit()

    row = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events, last_updated FROM characters WHERE session_id = ? AND name = ?",
        (session_id, char_name),
    )
    r = row[0]
    return {"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3]), "lastUpdated": r[4]}


@router.post("/update")
async def trigger_meta(session_id: str, body: dict):
    chapter_id = body.get("chapterId")
    db = await get_db()

    session_row = await db.execute_fetchall("SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,))
    if not session_row:
        raise HTTPException(404, "Session not found")

    from app.config import DATA_DIR
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{session_row[0][0]}.json").read_text(encoding="utf-8"))

    chunks = []
    if chapter_id:
        chunk_rows = await db.execute_fetchall(
            'SELECT id, chapter_id, "order", active_version, versions FROM chunks WHERE chapter_id = ? ORDER BY "order"',
            (chapter_id,),
        )
        chunks = [{"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]} for r in chunk_rows]

    interval = settings.get("chunkUpdateInterval", 10)
    recent = chunks[-interval:]
    result = await run_meta_analysis(session_id, recent, settings)
    return result


@router.post("/consolidate")
async def consolidate(session_id: str):
    db = await get_db()

    session_row = await db.execute_fetchall("SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,))
    if not session_row:
        raise HTTPException(404, "Session not found")

    from app.config import DATA_DIR
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{session_row[0][0]}.json").read_text(encoding="utf-8"))

    char_rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?", (session_id,)
    )
    characters = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in char_rows]

    fact_rows = await db.execute_fetchall("SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,))
    facts = [r[0] for r in fact_rows]

    consolidate_messages = [
        {"role": "system", "content": """You are a data compressor for character sheets and story facts.

Your job: AGGRESSIVELY consolidate and compress. Be ruthless about merging.

KEY EVENTS rules:
- Multiple events about the SAME topic MUST be merged into ONE entry.
- Keep events VAGUE and SHORT. No unnecessary details.
- Max 7 events per character. If over 7, merge related events aggressively.

TRAITS rules:
- Personality and behavioral ONLY. No physical descriptions.
- Max 6 traits per character. Merge similar ones.

FACTS rules:
- VAGUE and HIGH LEVEL.
- Multiple facts about the same subject MUST be merged into ONE.
- Max 10 facts total. Merge aggressively.
- Remove facts that are obvious from character sheets.

Return ONLY valid JSON:
{
  "characters": [{ "name": "", "currentState": "", "traits": [], "keyEvents": [] }],
  "facts": ["fact1", "fact2"]
}"""},
        {"role": "user", "content": f"## Characters\n{json.dumps(characters, indent=2)}\n\n## Facts\n{json.dumps(facts, indent=2)}\n\nConsolidate and compress. Return only the JSON."},
    ]

    result = await generate_completion(
        consolidate_messages,
        temperature=0.2,
        max_tokens=(settings.get("maxTokens", 4096)) * 3,
    )

    parsed = None
    try:
        parsed = json.loads(result["narrative"])
    except (json.JSONDecodeError, TypeError):
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", result["narrative"]) or re.search(r"\{[\s\S]*\}", result["narrative"])
        if m:
            try:
                parsed = json.loads(m.group(1) if m.lastindex else m.group(0))
            except (json.JSONDecodeError, TypeError):
                pass

    now = datetime.now(timezone.utc).isoformat()
    if parsed and parsed.get("characters"):
        for update in parsed["characters"]:
            await db.execute(
                "UPDATE characters SET current_state = ?, traits = ?, key_events = ?, last_updated = ? WHERE session_id = ? AND name = ?",
                (update.get("currentState", ""), json.dumps(update.get("traits", [])),
                 json.dumps(update.get("keyEvents", [])), now, session_id, update["name"]),
            )

    if parsed and parsed.get("facts"):
        await db.execute("DELETE FROM facts WHERE session_id = ?", (session_id,))
        for fact in parsed["facts"]:
            await db.execute("INSERT INTO facts (session_id, fact, created_at) VALUES (?,?,?)", (session_id, fact, now))

    await db.commit()

    updated_chars = await list_characters(session_id)
    return {"characters": updated_chars, "facts": parsed.get("facts", facts) if parsed else facts}


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
