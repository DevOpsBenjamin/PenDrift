"""Generate evocative chapter titles from narrative excerpts."""
from __future__ import annotations

import asyncio
import json
import logging

from app.database import get_db
from app.services import llm_activity
from app.services.llm import _build_body, _get_lock, generate_completion, llama_sse_completion
from app.services.job_manager import Job
from app.utils.grammars import TITLE_GRAMMAR

log = logging.getLogger("pendrift.title_gen")


def _get_narrative(chunk: dict) -> str:
    versions = chunk.get("versions")
    if versions:
        if isinstance(versions, str):
            versions = json.loads(versions)
        idx = chunk.get("active_version", chunk.get("activeVersion", 0))
        return versions[idx]["narrative"]
    return chunk.get("narrative", "")


async def generate_chapter_title(
    session_id: str, chunks: list[dict], settings: dict, chapter_order: int,
    *, job: Job | None = None,
) -> str:
    fallback = f"Chapter {chapter_order + 1}"
    if not chunks:
        return fallback

    try:
        messages = [
            {"role": "system", "content": "You are a chapter title generator for a novel. You will receive excerpts from the beginning, middle, and end of a chapter, plus a meta-analysis summary. Suggest a short, evocative chapter title (3-6 words max). Return JSON with your reasoning in `thinking` and the final title in `title` (no surrounding quotes)."},
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

        if job is None:
            result = await generate_completion(
                messages,
                temperature=0.7,
                max_tokens=400,
                grammar=TITLE_GRAMMAR,
                kind="title",
                session_id=session_id,
            )
            raw = result["raw"]
        else:
            # Stream LLM events into the job so the toast shows live progress.
            body = _build_body(messages, temperature=0.7, max_tokens=400, grammar=TITLE_GRAMMAR)
            call = llm_activity.register("title", session_id)
            llm_activity.attach_task(call, asyncio.current_task())
            full: list[str] = []
            usage: dict = {}
            model_name = ""
            try:
                async with _get_lock():
                    llm_activity.mark_running(call)
                    job.emit({"type": "llm_start", "kind": "title", "callId": call.id})
                    async for ev in llama_sse_completion(body, activity_call=call, kind="title"):
                        if ev["type"] == "delta":
                            full.append(ev["text"])
                        elif ev["type"] == "model":
                            model_name = ev["name"]
                        elif ev["type"] == "usage":
                            usage = ev["data"]
                        job.emit(ev)
                stats = {
                    "promptTokens": usage.get("prompt_tokens"),
                    "completionTokens": usage.get("completion_tokens"),
                    "totalTokens": usage.get("total_tokens"),
                }
                llm_activity.mark_done(call, stats=stats, model=model_name, raw_response="".join(full))
                job.emit({"type": "llm_done", "stats": stats, "modelName": model_name})
                raw = "".join(full)
            except asyncio.CancelledError:
                llm_activity.mark_done(call, error="cancelled", raw_response="".join(full) or None)
                raise
            except Exception as e:
                llm_activity.mark_done(call, error=str(e), raw_response="".join(full) or None)
                raise

        parsed = json.loads(raw)
        title = (parsed.get("title") or "").strip()
        if title and len(title) < 80:
            return title

    except Exception as e:
        log.error("Title generation failed: %s", e)

    return fallback
