"""Meta-analysis pipeline: analyze narrative, update characters, extract facts."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.database import get_db
from app.services.llm import run_llm_buffered
from app.services.job_manager import Job
from app.services.prompts import build_initial_meta_messages, build_meta_analysis_messages
from app.services.prompts_registry import effective_prompt

log = logging.getLogger("pendrift.meta")


async def apply_initial_meta_to_session(
    session_id: str, template: dict, settings: dict, *, job: Job | None = None,
) -> dict:
    """Run the initial meta call and apply its output to the session's DB rows.

    Designed to run as a background job after session creation. The session
    row already exists with `initial_meta_status = 'pending'` and characters
    seeded from `template.initialState` as a legacy fallback. This function
    upgrades that fallback to the structured per-character fields, populates
    `pending_milestones` and `important_facts`, logs to `meta_history`, and
    flips the status to `done` (or `failed`).

    Returns the same shape as `run_initial_meta_analysis` plus the applied
    flag, so the job emit can describe what landed.
    """
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "UPDATE sessions SET initial_meta_status = 'running' WHERE id = ?",
        (session_id,),
    )
    await db.commit()

    initial = await run_initial_meta_analysis(template, settings, job=job)

    if not initial.get("ok"):
        await db.execute(
            "UPDATE sessions SET initial_meta_status = 'failed' WHERE id = ?",
            (session_id,),
        )
        # Log the failure to meta_history so the user can see what happened.
        await db.execute(
            "INSERT INTO meta_history (session_id, timestamp, chunk_range, status, result, raw_response) VALUES (?,?,?,?,?,?)",
            (
                session_id, now,
                json.dumps({"kind": "initial", "from": None, "to": None, "count": 0}),
                "failed",
                json.dumps({
                    "characters": initial.get("characters") or [],
                    "pendingMilestones": initial.get("pendingMilestones") or [],
                    "importantFacts": initial.get("importantFacts") or [],
                    "consistencyFlags": initial.get("consistencyFlags") or [],
                }),
                initial.get("raw") or "",
            ),
        )
        await db.commit()
        return initial

    # Apply per-character structured fields. Characters already exist as legacy
    # fallback rows (seeded with initialState in sessions.py); we UPDATE them
    # in place rather than INSERT.
    initial_chars_by_name: dict[str, dict] = {
        (c.get("name") or "").strip(): c for c in initial.get("characters") or []
        if c.get("name")
    }
    for name, meta_char in initial_chars_by_name.items():
        existing = await db.execute_fetchall(
            "SELECT 1 FROM characters WHERE session_id = ? AND name = ?",
            (session_id, name),
        )
        if existing:
            await db.execute(
                """UPDATE characters SET
                    current_state = ?, identity = ?, voice = ?, appearance = ?,
                    backstory = ?, masked_intents = ?, last_updated = ?
                   WHERE session_id = ? AND name = ?""",
                (
                    meta_char.get("currentState") or "",
                    meta_char.get("identity") or "",
                    meta_char.get("voice") or "",
                    meta_char.get("appearance") or "",
                    meta_char.get("backstory") or "",
                    json.dumps(meta_char.get("maskedIntents") or []),
                    now, session_id, name,
                ),
            )
        else:
            # Initial meta returned a character not seeded from template (rare —
            # template structure mismatch). Insert it so it's not lost.
            await db.execute(
                """INSERT INTO characters (
                    session_id, name, current_state, traits, key_events,
                    identity, voice, appearance, backstory, backstory_additions,
                    masked_intents, last_updated
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id, name,
                    meta_char.get("currentState") or "",
                    "[]", "[]",
                    meta_char.get("identity") or "",
                    meta_char.get("voice") or "",
                    meta_char.get("appearance") or "",
                    meta_char.get("backstory") or "",
                    "[]",
                    json.dumps(meta_char.get("maskedIntents") or []),
                    now,
                ),
            )

    # Session-level: pending milestones + facts.
    pending_milestones = initial.get("pendingMilestones") or []
    important_facts = initial.get("importantFacts") or []
    await db.execute(
        "UPDATE sessions SET pending_milestones = ?, initial_meta_status = 'done' WHERE id = ?",
        (json.dumps(pending_milestones), session_id),
    )
    # Important facts: clear (in case any were seeded earlier via legacy paths)
    # then insert the new list. New sessions start with no facts, so clear is
    # usually a no-op.
    await db.execute("DELETE FROM facts WHERE session_id = ?", (session_id,))
    for fact in important_facts:
        await db.execute(
            "INSERT INTO facts (session_id, fact, created_at) VALUES (?,?,?)",
            (session_id, fact, now),
        )

    await db.execute(
        "INSERT INTO meta_history (session_id, timestamp, chunk_range, status, result, raw_response) VALUES (?,?,?,?,?,?)",
        (
            session_id, now,
            json.dumps({"kind": "initial", "from": None, "to": None, "count": 0}),
            "success",
            json.dumps({
                "characters": initial.get("characters") or [],
                "pendingMilestones": pending_milestones,
                "importantFacts": important_facts,
                "consistencyFlags": initial.get("consistencyFlags") or [],
            }),
            initial.get("raw") or "",
        ),
    )
    await db.commit()

    return {**initial, "applied": True}


async def run_initial_meta_analysis(
    template: dict, settings: dict, *, job: Job | None = None,
) -> dict:
    """Run the initial meta call for a session being created. Returns the
    parsed structured state — caller is responsible for persisting it to DB.

    On failure (LLM down, parse error, schema mismatch), returns an empty
    fallback shape so the caller can still seed the session with legacy
    behavior. Failures are logged.

    Returned shape:
        {
            "characters": [{name, identity, voice, appearance, backstory,
                            currentState, maskedIntents}, ...],
            "pendingMilestones": [...],
            "importantFacts": [...],
            "consistencyFlags": [...],
            "raw": str,             # raw LLM response for meta_history
            "ok": bool,             # True iff LLM succeeded and parsed cleanly
        }
    """
    variables = template.get("variables") or {}
    messages = build_initial_meta_messages(
        template=template, variables=variables, settings=settings,
    )

    raw_response = ""
    try:
        response = await run_llm_buffered(
            messages,
            settings=settings,
            kind="meta_initial",
            session_id=None,
            job=job,
            temperature=0.2,
            max_tokens=(settings.get("maxTokens", 4096)) * 2,
        )
        raw_response = response["raw"]
        parsed = json.loads(raw_response)
    except Exception as e:
        log.error("Initial meta failed: %s", e)
        return {
            "characters": [], "pendingMilestones": [], "importantFacts": [],
            "consistencyFlags": [f"Initial meta call failed: {e}"],
            "raw": raw_response, "ok": False,
        }

    chars = parsed.get("characters") or []
    if not isinstance(chars, list):
        log.warning("Initial meta returned non-list characters; ignoring")
        chars = []

    return {
        "characters": chars,
        "pendingMilestones": parsed.get("pendingMilestones") or [],
        "importantFacts": parsed.get("importantFacts") or [],
        "consistencyFlags": parsed.get("consistencyFlags") or [],
        "raw": raw_response,
        "ok": True,
    }


_FULL_CHAR_SELECT = (
    "name, current_state, traits, key_events, identity, voice, appearance, "
    "backstory, backstory_additions, masked_intents, last_updated"
)


def _row_to_char_dict(r) -> dict:
    return {
        "name": r[0],
        "currentState": r[1] or "",
        "traits": json.loads(r[2]) if r[2] else [],
        "keyEvents": json.loads(r[3]) if r[3] else [],
        "identity": r[4] or "",
        "voice": r[5] or "",
        "appearance": r[6] or "",
        "backstory": r[7] or "",
        "backstoryAdditions": json.loads(r[8]) if r[8] else [],
        "maskedIntents": json.loads(r[9]) if r[9] else [],
        "lastUpdated": r[10],
    }


async def _apply_character_update(db, session_id: str, update: dict, now: str) -> None:
    """Apply one characterUpdates entry to a character row.

    - currentState: replace
    - traits, keyEvents: APPEND (the model emits new-this-cycle deltas)
    - identityUpdate, voiceUpdate, appearanceUpdate: replace the field if present
    - backstoryAdditions: append to existing array
    - maskedIntentResolutions: remove the named intents from masked_intents,
      and integrate `as` text into identity (replace) or backstory_additions (append)
    """
    name = update.get("name")
    if not name:
        return

    rows = await db.execute_fetchall(
        f"SELECT {_FULL_CHAR_SELECT} FROM characters WHERE session_id = ? AND name = ?",
        (session_id, name),
    )
    if not rows:
        log.warning("characterUpdate for unknown character %r — skipping", name)
        return
    cur = _row_to_char_dict(rows[0])

    # Append-only deltas. The meta prompt emits new-this-cycle items; we extend.
    new_traits = cur["traits"] + [t for t in (update.get("traits") or []) if t]
    new_events = cur["keyEvents"] + [e for e in (update.get("keyEvents") or []) if e]
    new_backstory_additions = cur["backstoryAdditions"] + [
        b for b in (update.get("backstoryAdditions") or []) if b
    ]

    # Replaceable fields — only overwrite if the meta emitted a non-empty value.
    new_identity = update["identityUpdate"] if update.get("identityUpdate") else cur["identity"]
    new_voice = update["voiceUpdate"] if update.get("voiceUpdate") else cur["voice"]
    new_appearance = update["appearanceUpdate"] if update.get("appearanceUpdate") else cur["appearance"]

    # Masked intent resolutions: remove from masked_intents, integrate per `integratesInto`.
    remaining_intents = list(cur["maskedIntents"])
    for resolution in update.get("maskedIntentResolutions") or []:
        intent_text = (resolution.get("intent") or "").strip()
        if intent_text and intent_text in remaining_intents:
            remaining_intents.remove(intent_text)
        target = (resolution.get("integratesInto") or "").lower()
        as_text = (resolution.get("as") or "").strip()
        if target == "identity" and as_text:
            new_identity = as_text  # the resolution's integrated text becomes the new identity baseline
        elif target == "backstory_additions" and as_text:
            new_backstory_additions.append(as_text)
        # target=null or unknown: just remove from masked_intents, no integration

    await db.execute(
        f"""UPDATE characters SET
            current_state = ?, traits = ?, key_events = ?,
            identity = ?, voice = ?, appearance = ?,
            backstory_additions = ?, masked_intents = ?,
            last_updated = ?
            WHERE session_id = ? AND name = ?""",
        (
            update.get("currentState", cur["currentState"]) or cur["currentState"],
            json.dumps(new_traits),
            json.dumps(new_events),
            new_identity, new_voice, new_appearance,
            json.dumps(new_backstory_additions),
            json.dumps(remaining_intents),
            now, session_id, name,
        ),
    )


async def _apply_milestone_changes(db, session_id: str, result: dict) -> None:
    """Move achieved milestones from pending → achieved. Obsolete milestones
    surface in consistencyFlags only — never auto-removed (director keeps agency).
    """
    achieved_names = [n for n in (result.get("milestonesAchieved") or []) if n]
    if not achieved_names:
        return

    row = await db.execute_fetchall(
        "SELECT pending_milestones, achieved_milestones FROM sessions WHERE id = ?",
        (session_id,),
    )
    if not row:
        return
    pending = json.loads(row[0][0]) if row[0][0] else []
    achieved = json.loads(row[0][1]) if row[0][1] else []

    moved_any = False
    for name in achieved_names:
        match = next((m for m in pending if m == name or m.startswith(name + ":") or name in m), None)
        if match:
            pending.remove(match)
            achieved.append(match)
            moved_any = True
        else:
            log.info("milestonesAchieved %r did not match any pending milestone — ignoring", name)

    if moved_any:
        await db.execute(
            "UPDATE sessions SET pending_milestones = ?, achieved_milestones = ? WHERE id = ?",
            (json.dumps(pending), json.dumps(achieved), session_id),
        )


async def run_meta_analysis(
    session_id: str, recent_chunks: list[dict], settings: dict,
    *, job: Job | None = None, director_note: str | None = None,
) -> dict:
    """Regular meta call. If `director_note` is provided, the prompt enters
    cleanup mode — see meta.md "Cleanup mode" section.
    """
    db = await get_db()

    rows = await db.execute_fetchall(
        f"SELECT {_FULL_CHAR_SELECT} FROM characters WHERE session_id = ?",
        (session_id,),
    )
    characters = [_row_to_char_dict(r) for r in rows]

    fact_rows = await db.execute_fetchall(
        "SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,)
    )
    important_facts = [r[0] for r in fact_rows]

    if not recent_chunks and not director_note:
        return {"characters": characters, "consistencyFlags": [], "importantFacts": []}

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
        director_note=director_note,
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

    for update in result.get("characterUpdates") or []:
        await _apply_character_update(db, session_id, update, now)

    for new_char in result.get("newCharacters") or []:
        if not new_char.get("name"):
            continue
        existing = await db.execute_fetchall(
            "SELECT 1 FROM characters WHERE session_id = ? AND name = ?",
            (session_id, new_char["name"]),
        )
        if not existing:
            await db.execute(
                """INSERT INTO characters (
                    session_id, name, current_state, traits, key_events, last_updated
                ) VALUES (?,?,?,?,?,?)""",
                (
                    session_id, new_char["name"],
                    new_char.get("currentState", ""),
                    json.dumps(new_char.get("traits") or []),
                    json.dumps(new_char.get("keyEvents") or []),
                    now,
                ),
            )

    if "importantFacts" in result:
        await db.execute("DELETE FROM facts WHERE session_id = ?", (session_id,))
        for fact in result.get("importantFacts") or []:
            await db.execute(
                "INSERT INTO facts (session_id, fact, created_at) VALUES (?,?,?)",
                (session_id, fact, now),
            )

    await _apply_milestone_changes(db, session_id, result)

    # Surface obsolete milestones as consistencyFlags so the director sees them.
    obsolete = result.get("milestonesObsolete") or []
    extra_flags: list[str] = []
    for entry in obsolete:
        name = entry.get("name") if isinstance(entry, dict) else str(entry)
        reason = entry.get("reason") if isinstance(entry, dict) else ""
        extra_flags.append(f"Milestone obsolete — {name}: {reason}")
    proposed = result.get("milestonesProposed") or []
    for entry in proposed:
        name = entry.get("name") if isinstance(entry, dict) else str(entry)
        desc = entry.get("description") if isinstance(entry, dict) else ""
        extra_flags.append(f"Milestone proposed — {name}: {desc}")

    chunk_ids = [c.get("id", "") for c in recent_chunks]
    await db.execute(
        "INSERT INTO meta_history (session_id, timestamp, chunk_range, status, result, raw_response) VALUES (?,?,?,?,?,?)",
        (
            session_id, now,
            json.dumps({
                "from": chunk_ids[0] if chunk_ids else None,
                "to": chunk_ids[-1] if chunk_ids else None,
                "count": len(recent_chunks),
                "kind": "cleanup" if director_note else "regular",
            }),
            "success",
            json.dumps({
                "characterUpdates": result.get("characterUpdates") or [],
                "newCharacters": result.get("newCharacters") or [],
                "consistencyFlags": (result.get("consistencyFlags") or []) + extra_flags,
                "importantFacts": result.get("importantFacts") or [],
                "milestonesAchieved": result.get("milestonesAchieved") or [],
                "milestonesObsolete": obsolete,
                "milestonesProposed": proposed,
            }),
            raw_response,
        ),
    )
    await db.commit()

    rows = await db.execute_fetchall(
        f"SELECT {_FULL_CHAR_SELECT} FROM characters WHERE session_id = ?",
        (session_id,),
    )
    updated_chars = [_row_to_char_dict(r) for r in rows]

    return {
        "characters": updated_chars,
        "consistencyFlags": (result.get("consistencyFlags") or []) + extra_flags,
        "newCharacters": result.get("newCharacters") or [],
        "importantFacts": result.get("importantFacts") or [],
        "milestonesAchieved": result.get("milestonesAchieved") or [],
        "milestonesObsolete": obsolete,
    }
