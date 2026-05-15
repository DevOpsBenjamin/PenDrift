"""One-off cleanup: normalize typographic quote variants in stored data.

Walks every template JSON file + DB rows that feed back into LLM prompts,
applies `normalize_quotes`, and writes back when a string actually changed.
Idempotent — running again on already-clean data is a no-op (every row is
read, the regex returns identical text, the row stays untouched).

Skips:
- chunks (those are RP outputs; preserving narrative content as-is is more
  important than uniform quoting)
- meta_history (frozen archive)
- variables{} in templates (variable defaults are usually proper nouns and
  not the source of pollution)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR
from app.database import get_db
from app.utils.quote_normalize import normalize_quotes

log = logging.getLogger("pendrift.quote_cleanup")

_TEMPLATES_DIR = DATA_DIR / "presets" / "templates"

# Top-level template fields whose plain-string content may carry pollution.
_TPL_STRING_FIELDS = ("description", "scenario", "systemPromptAdditions")
# Top-level template fields holding a list of plain strings.
_TPL_ARRAY_FIELDS = ("milestones", "maskedIntents")
# Per-character fields inside template.characters[].
_TPL_CHAR_FIELDS = ("description", "initialState")


def _normalize_in_place(obj: dict, key: str) -> bool:
    """Normalize obj[key] if it's a non-empty string. Returns True if changed."""
    val = obj.get(key)
    if not isinstance(val, str) or not val:
        return False
    new_val = normalize_quotes(val)
    if new_val != val:
        obj[key] = new_val
        return True
    return False


def _normalize_array(obj: dict, key: str) -> bool:
    """Normalize each string in obj[key] (a list). Returns True if any element changed."""
    arr = obj.get(key)
    if not isinstance(arr, list):
        return False
    changed = False
    new_arr = []
    for item in arr:
        if isinstance(item, str):
            new_item = normalize_quotes(item)
            if new_item != item:
                changed = True
            new_arr.append(new_item)
        else:
            new_arr.append(item)
    if changed:
        obj[key] = new_arr
    return changed


def _clean_template_file(path: Path) -> bool:
    """Returns True if the file was rewritten."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Skip %s: %s", path, e)
        return False
    if not isinstance(data, dict):
        return False

    changed = False
    for fld in _TPL_STRING_FIELDS:
        changed |= _normalize_in_place(data, fld)
    for fld in _TPL_ARRAY_FIELDS:
        changed |= _normalize_array(data, fld)
    chars = data.get("characters")
    if isinstance(chars, list):
        for c in chars:
            if isinstance(c, dict):
                for cf in _TPL_CHAR_FIELDS:
                    changed |= _normalize_in_place(c, cf)

    if changed:
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("Failed to write %s: %s", path, e)
            return False
    return changed


async def _clean_db_characters_and_facts() -> tuple[int, int]:
    """Returns (characters_touched, facts_touched)."""
    db = await get_db()
    chars_changed = 0
    facts_changed = 0

    cursor = await db.execute(
        "SELECT session_id, name, current_state, traits, key_events FROM characters"
    )
    rows = await cursor.fetchall()
    for row in rows:
        sid, name, current_state, traits_json, events_json = row
        new_state = normalize_quotes(current_state) if current_state else current_state
        new_traits_json = traits_json
        new_events_json = events_json

        try:
            traits = json.loads(traits_json or "[]")
            traits_dirty = False
            new_traits = []
            for t in traits:
                if isinstance(t, str):
                    nt = normalize_quotes(t)
                    if nt != t:
                        traits_dirty = True
                    new_traits.append(nt)
                else:
                    new_traits.append(t)
            if traits_dirty:
                new_traits_json = json.dumps(new_traits, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

        try:
            events = json.loads(events_json or "[]")
            events_dirty = False
            new_events = []
            for e in events:
                if isinstance(e, str):
                    ne = normalize_quotes(e)
                    if ne != e:
                        events_dirty = True
                    new_events.append(ne)
                else:
                    new_events.append(e)
            if events_dirty:
                new_events_json = json.dumps(new_events, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

        if new_state != current_state or new_traits_json != traits_json or new_events_json != events_json:
            await db.execute(
                "UPDATE characters SET current_state = ?, traits = ?, key_events = ? WHERE session_id = ? AND name = ?",
                (new_state, new_traits_json, new_events_json, sid, name),
            )
            chars_changed += 1

    cursor = await db.execute("SELECT id, fact FROM facts")
    fact_rows = await cursor.fetchall()
    for fid, fact in fact_rows:
        new_fact = normalize_quotes(fact) if fact else fact
        if new_fact != fact:
            await db.execute("UPDATE facts SET fact = ? WHERE id = ?", (new_fact, fid))
            facts_changed += 1

    if chars_changed or facts_changed:
        await db.commit()

    return chars_changed, facts_changed


async def run_quote_cleanup() -> dict:
    """Top-level runner. Cleans templates + DB. Logs and returns counts."""
    template_files_touched = 0
    if _TEMPLATES_DIR.is_dir():
        for tdir in _TEMPLATES_DIR.iterdir():
            if not tdir.is_dir():
                continue
            for jf in tdir.glob("*.json"):
                if _clean_template_file(jf):
                    template_files_touched += 1

    chars_touched, facts_touched = await _clean_db_characters_and_facts()

    counts = {
        "templateFiles": template_files_touched,
        "characters": chars_touched,
        "facts": facts_touched,
    }
    if template_files_touched or chars_touched or facts_touched:
        log.info(
            "Quote cleanup normalized %d template file(s), %d character row(s), %d fact row(s).",
            template_files_touched, chars_touched, facts_touched,
        )
    return counts
