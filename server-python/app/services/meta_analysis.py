"""Meta-analysis pipeline: analyze narrative, update characters, extract facts."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.database import get_db
from app.services.llm import run_llm_buffered
from app.services.job_manager import Job
from app.services.prompts import build_meta_analysis_messages
from app.services.prompts_registry import effective_prompt

log = logging.getLogger("pendrift.meta")


async def run_meta_analysis(
    session_id: str, recent_chunks: list[dict], settings: dict,
    *, job: Job | None = None,
) -> dict:
    db = await get_db()

    # Load characters
    rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events, last_updated FROM characters WHERE session_id = ?",
        (session_id,),
    )
    characters = [
        {"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3]), "lastUpdated": r[4]}
        for r in rows
    ]

    # Load facts
    fact_rows = await db.execute_fetchall(
        "SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,)
    )
    important_facts = [r[0] for r in fact_rows]

    if not recent_chunks:
        return {"characters": characters, "consistencyFlags": [], "importantFacts": []}

    # Previous meta results (last 5 successful)
    meta_rows = await db.execute_fetchall(
        "SELECT result FROM meta_history WHERE session_id = ? AND status = 'success' ORDER BY id DESC LIMIT 5",
        (session_id,),
    )
    previous_meta = [{"result": json.loads(r[0])} for r in meta_rows]
    previous_meta.reverse()

    messages = build_meta_analysis_messages(
        characters=characters,
        recent_chunks=recent_chunks,
        important_facts=important_facts,
        meta_prompt=effective_prompt("meta", settings, settings.get("provider", "llama-server")),
        previous_meta_results=previous_meta,
    )

    raw_response = ""
    result = None
    now = datetime.now(timezone.utc).isoformat()

    try:
        response = await run_llm_buffered(
            messages,
            settings=settings,
            kind="meta",
            session_id=session_id,
            job=job,
            temperature=0.2,
            max_tokens=(settings.get("maxTokens", 4096)) * 2,
        )
        raw_response = response["raw"]
        result = json.loads(raw_response)
    except Exception as e:
        log.error("Meta-analysis failed: %s", e)
        chunk_ids = [c.get("id", "") for c in recent_chunks]
        await db.execute(
            "INSERT INTO meta_history (session_id, timestamp, chunk_range, status, error, raw_response) VALUES (?,?,?,?,?,?)",
            (session_id, now, json.dumps({"from": chunk_ids[0] if chunk_ids else None, "to": chunk_ids[-1] if chunk_ids else None}), "failed", str(e), raw_response),
        )
        await db.commit()
        return {"characters": characters, "consistencyFlags": [], "importantFacts": []}

    # Apply character updates
    for update in result.get("characterUpdates", []):
        await db.execute(
            """UPDATE characters SET current_state = ?, traits = ?, key_events = ?, last_updated = ?
               WHERE session_id = ? AND name = ?""",
            (update.get("currentState", ""), json.dumps(update.get("traits", [])),
             json.dumps(update.get("keyEvents", [])), now, session_id, update["name"]),
        )

    # Add new characters
    for new_char in result.get("newCharacters", []):
        existing = await db.execute_fetchall(
            "SELECT 1 FROM characters WHERE session_id = ? AND name = ?", (session_id, new_char["name"])
        )
        if not existing:
            await db.execute(
                "INSERT INTO characters (session_id, name, current_state, traits, key_events, last_updated) VALUES (?,?,?,?,?,?)",
                (session_id, new_char["name"], new_char.get("currentState", ""),
                 json.dumps(new_char.get("traits", [])), json.dumps(new_char.get("keyEvents", [])), now),
            )

    # REPLACE the facts list wholesale: the meta output IS the new list. This
    # is intentional — the meta prompt asks the model to decide keep/drop/merge
    # so the state stays tight as the story grows. Without wholesale replace,
    # the list would grow unbounded and pollute future generations.
    if "importantFacts" in result:
        await db.execute("DELETE FROM facts WHERE session_id = ?", (session_id,))
        for fact in result.get("importantFacts", []):
            await db.execute(
                "INSERT INTO facts (session_id, fact, created_at) VALUES (?,?,?)",
                (session_id, fact, now),
            )

    # Save meta history
    chunk_ids = [c.get("id", "") for c in recent_chunks]
    await db.execute(
        "INSERT INTO meta_history (session_id, timestamp, chunk_range, status, result, raw_response) VALUES (?,?,?,?,?,?)",
        (session_id, now,
         json.dumps({"from": chunk_ids[0] if chunk_ids else None, "to": chunk_ids[-1] if chunk_ids else None, "count": len(recent_chunks)}),
         "success", json.dumps({
             "characterUpdates": result.get("characterUpdates", []),
             "newCharacters": result.get("newCharacters", []),
             "consistencyFlags": result.get("consistencyFlags", []),
             "importantFacts": result.get("importantFacts", []),
         }), raw_response),
    )
    await db.commit()

    # Reload characters
    rows = await db.execute_fetchall(
        "SELECT name, current_state, traits, key_events FROM characters WHERE session_id = ?", (session_id,)
    )
    updated_chars = [{"name": r[0], "currentState": r[1], "traits": json.loads(r[2]), "keyEvents": json.loads(r[3])} for r in rows]

    return {
        "characters": updated_chars,
        "consistencyFlags": result.get("consistencyFlags", []),
        "newCharacters": result.get("newCharacters", []),
        "importantFacts": result.get("importantFacts", []),
    }
