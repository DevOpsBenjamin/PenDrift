"""Generate evocative chapter titles from narrative excerpts."""
from __future__ import annotations

import json
import logging

from app.database import get_db
from app.services.llm import generate_completion

log = logging.getLogger("pendrift.title_gen")


def _get_narrative(chunk: dict) -> str:
    versions = chunk.get("versions")
    if versions:
        if isinstance(versions, str):
            versions = json.loads(versions)
        idx = chunk.get("active_version", chunk.get("activeVersion", 0))
        return versions[idx]["narrative"]
    return chunk.get("narrative", "")


async def generate_chapter_title(session_id: str, chunks: list[dict], settings: dict, chapter_order: int) -> str:
    fallback = f"Chapter {chapter_order + 1}"
    if not chunks:
        return fallback

    try:
        messages = [
            {"role": "system", "content": "You are a chapter title generator for a novel. You will receive excerpts from the beginning, middle, and end of a chapter, plus a meta-analysis summary. Suggest a short, evocative chapter title (3-6 words max). Return ONLY the title, nothing else. No quotes, no explanation."},
        ]

        # First 2 chunks
        messages.append({"role": "user", "content": "This is the BEGINNING of the chapter:"})
        messages.append({"role": "assistant", "content": _get_narrative(chunks[0])[:500]})
        if len(chunks) >= 2:
            messages.append({"role": "assistant", "content": _get_narrative(chunks[1])[:500]})

        # Middle
        if len(chunks) >= 5:
            mid = len(chunks) // 2
            messages.append({"role": "user", "content": "This is the MIDDLE of the chapter:"})
            messages.append({"role": "assistant", "content": _get_narrative(chunks[mid])[:500]})

        # Last 2
        if len(chunks) >= 3:
            messages.append({"role": "user", "content": "This is the END of the chapter:"})
            if len(chunks) >= 4:
                messages.append({"role": "assistant", "content": _get_narrative(chunks[-2])[:500]})
            messages.append({"role": "assistant", "content": _get_narrative(chunks[-1])[:500]})

        # Meta summary
        db = await get_db()
        char_rows = await db.execute_fetchall(
            "SELECT name, current_state FROM characters WHERE session_id = ?", (session_id,)
        )
        fact_rows = await db.execute_fetchall(
            "SELECT fact FROM facts WHERE session_id = ? ORDER BY id DESC LIMIT 5", (session_id,)
        )

        meta_summary = "Meta-analysis summary:\n"
        meta_summary += "Characters: " + "; ".join(f"{r[0]} ({r[1]})" for r in char_rows) + "\n"
        if fact_rows:
            meta_summary += "Key facts: " + "; ".join(r[0] for r in fact_rows)
        messages.append({"role": "user", "content": meta_summary + "\n\nBased on all of the above, suggest a chapter title."})

        result = await generate_completion(
            messages,
            temperature=0.7,
            max_tokens=100,
        )

        title = result["narrative"]
        if title and len(title) < 80:
            return title.replace('"', "").replace("'", "").strip()

    except Exception as e:
        log.error("Title generation failed: %s", e)

    return fallback
