"""Meta-analysis pipeline: analyze narrative, update characters, extract facts."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from app.database import get_db
from app.services.llm import generate_completion
from app.services.prompts import build_meta_analysis_messages

log = logging.getLogger("pendrift.meta")


def _try_parse_json(text: str) -> dict | None:
    # Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    # Find JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


async def _fix_json_with_utility(raw_text: str, settings: dict, session_id: str) -> dict | None:
    fixer_prompt = settings.get("formatFixerPrompt", "Extract and return only valid JSON from the following text.")
    messages = [
        {"role": "system", "content": fixer_prompt},
        {"role": "user", "content": raw_text},
    ]
    result = await generate_completion(
        messages,
        temperature=0.1,
        max_tokens=settings.get("maxTokens", 4096),
    )
    return _try_parse_json(result["narrative"])


async def run_meta_analysis(session_id: str, recent_chunks: list[dict], settings: dict) -> dict:
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
        meta_prompt=settings.get("metaPrompt", ""),
        previous_meta_results=previous_meta,
    )

    raw_response = ""
    result = None
    now = datetime.now(timezone.utc).isoformat()

    try:
        response = await generate_completion(
            messages,
            temperature=0.2,
            max_tokens=(settings.get("maxTokens", 4096)) * 2,
        )
        raw_response = response["raw"]
        result = _try_parse_json(response["narrative"])

        if not result:
            log.info("Meta JSON parse failed, trying format fixer...")
            result = await _fix_json_with_utility(response["raw"], settings, session_id)

        if not result:
            raise ValueError("Could not parse meta-analysis response even after format fixing")

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

    # Add new facts (deduplicate)
    for fact in result.get("importantFacts", []):
        existing = await db.execute_fetchall(
            "SELECT 1 FROM facts WHERE session_id = ? AND fact = ?", (session_id, fact)
        )
        if not existing:
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
