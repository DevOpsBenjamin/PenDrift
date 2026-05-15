"""Template CRUD routes — folder-per-template storage with versioning.

See app/services/template_store.py for the disk layout.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.services import template_store, job_manager

log = logging.getLogger("pendrift.templates")
router = APIRouter()


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# Fields not worth diffing (cover image filename is folder-scoped metadata,
# id must match by construction). Keep the rest verbatim.
_DIFF_IGNORED_FIELDS = ("coverImage", "_avatarAvailable", "_saved")


def _template_for_diff(body: dict) -> dict:
    """Strip noisy fields and serialize in stable order for a clean diff."""
    return {k: v for k, v in body.items() if k not in _DIFF_IGNORED_FIELDS}


def _compute_diff(old: dict, new: dict) -> list[dict]:
    """Return structured diff rows comparing pretty-printed JSON of two templates.

    Each row is `{kind: 'context'|'add'|'remove'|'hunk', text: str}`. Designed
    for a git-style side-by-side render in the UI."""
    old_lines = json.dumps(_template_for_diff(old), indent=2, ensure_ascii=False).splitlines()
    new_lines = json.dumps(_template_for_diff(new), indent=2, ensure_ascii=False).splitlines()
    rows: list[dict] = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=3):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("@@"):
            rows.append({"kind": "hunk", "text": line})
        elif line.startswith("+"):
            rows.append({"kind": "add", "text": line[1:]})
        elif line.startswith("-"):
            rows.append({"kind": "remove", "text": line[1:]})
        elif line.startswith(" "):
            rows.append({"kind": "context", "text": line[1:]})
        else:
            rows.append({"kind": "context", "text": line})
    return rows


@router.get("")
async def list_templates():
    return template_store.list_templates()


@router.get("/{template_id}")
async def get_template(template_id: str):
    data = template_store.load_current(template_id)
    if data is None:
        raise HTTPException(404, f"Template '{template_id}' not found")
    return data


@router.post("")
async def save_template(body: dict):
    """Save a template. If new, creates folder + 0001.json. If existing,
    appends a new version (every edit is versioned — no in-place overwrite)."""
    tid = body.get("id")
    if not tid:
        raise HTTPException(400, "Template id is required")
    folder = template_store.template_dir(tid)
    if template_store.is_template_folder(folder):
        new_body, _version = template_store.add_version(tid, body, action="edit")
        return new_body
    try:
        return template_store.create_new_template(tid, body, action="manual-create")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    template_store.delete_template(template_id)
    return {"ok": True}


# ── Cover image ─────────────────────────────────────────

@router.get("/{template_id}/image")
async def get_template_image(template_id: str):
    folder = template_store.template_dir(template_id)
    img = template_store.find_image(folder)
    if img is None:
        raise HTTPException(404, "No cover image for this template")
    return FileResponse(img)


@router.post("/{template_id}/image")
async def upload_template_image(template_id: str, file: UploadFile = File(...)):
    if not template_store.is_template_folder(template_store.template_dir(template_id)):
        raise HTTPException(404, f"Template '{template_id}' not found")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in template_store.ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"Unsupported image type: {ext or 'unknown'}")
    contents = await file.read()
    filename = template_store.write_image(template_id, contents, ext)
    # Update the current version to record the cover image presence
    current = template_store.load_current(template_id) or {}
    current["coverImage"] = filename
    template_store.save_in_place(template_id, current)
    return {"ok": True, "coverImage": filename, "template": current}


@router.delete("/{template_id}/image")
async def delete_template_image(template_id: str):
    if not template_store.is_template_folder(template_store.template_dir(template_id)):
        raise HTTPException(404, "Template not found")
    template_store.delete_image(template_id)
    current = template_store.load_current(template_id) or {}
    current.pop("coverImage", None)
    template_store.save_in_place(template_id, current)
    return {"ok": True, "template": current}


# ── Versioning ──────────────────────────────────────────

@router.get("/{template_id}/versions")
async def list_template_versions(template_id: str):
    if not template_store.is_template_folder(template_store.template_dir(template_id)):
        raise HTTPException(404, "Template not found")
    return template_store.list_versions(template_id)


@router.get("/{template_id}/versions/{version}")
async def get_template_version(template_id: str, version: str):
    data = template_store.load_version(template_id, version)
    if data is None:
        raise HTTPException(404, "Version not found")
    return data


@router.get("/{template_id}/diff")
async def diff_template_versions(
    template_id: str,
    from_: str = Query("", alias="from"),
    to: str = "",
):
    """Compute the structured diff between two versions of a template. Use
    `from` and `to` query params (e.g. ?from=0001&to=0002). The same diff
    renderer used by the rerun preview."""
    if not from_ or not to:
        raise HTTPException(400, "Both 'from' and 'to' query params are required")
    old = template_store.load_version(template_id, from_)
    new = template_store.load_version(template_id, to)
    if old is None or new is None:
        raise HTTPException(404, "One or both versions not found")
    return {"from": from_, "to": to, "diff": _compute_diff(old, new)}


@router.post("/{template_id}/checkpoint")
async def checkpoint_template(template_id: str):
    """Snapshot the current state as a new version. Useful before risky edits
    or to manually preserve a 'good' state."""
    current = template_store.load_current(template_id)
    if current is None:
        raise HTTPException(404, "Template not found")
    body, version = template_store.add_version(
        template_id, current, action="manual-checkpoint"
    )
    return {"ok": True, "version": version, "template": body}


@router.post("/{template_id}/restore/{version}")
async def restore_template_version(template_id: str, version: str):
    """Make `version` the new latest by copying it to a fresh version slot."""
    try:
        body, new_version = template_store.restore_version(template_id, version)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "version": new_version, "template": body}


# ── Sources (original chub cards attached to the template) ──

@router.get("/{template_id}/sources")
async def list_template_sources(template_id: str):
    if not template_store.is_template_folder(template_store.template_dir(template_id)):
        raise HTTPException(404, "Template not found")
    return template_store.list_sources(template_id)


@router.post("/{template_id}/sources")
async def attach_template_source(template_id: str, body: dict):
    """Attach a card JSON to an existing template. Useful for legacy templates
    that were imported before sources were preserved. Body: {card: {...}}.

    Side effects (best-effort):
    - Normalizes V2-wrapped cards to flat shape before saving.
    - If the template has no cover image yet and the card carries an `avatar`
      URL, fetches and attaches it as the cover.
    """
    card = body.get("card")
    if not isinstance(card, dict):
        if isinstance(card, str):
            import json as _json
            try:
                card = _json.loads(card)
            except _json.JSONDecodeError as e:
                raise HTTPException(400, f"Invalid JSON in 'card': {e}")
        else:
            raise HTTPException(400, "Body must include 'card' (object or JSON string)")

    # Normalize so what we persist is the flat shape (consistent with imports)
    from app.services.chub_importer import _normalize_card, download_card_avatar
    normalized = _normalize_card(card)

    try:
        filename = template_store.attach_source(template_id, normalized)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    cover_added = False
    current = template_store.load_current(template_id) or {}
    if not current.get("coverImage"):
        avatar = await download_card_avatar(normalized)
        if avatar:
            content, ext = avatar
            try:
                cover_filename = template_store.write_image(template_id, content, ext)
                current["coverImage"] = cover_filename
                template_store.save_in_place(template_id, current)
                cover_added = True
            except (ValueError, OSError):
                pass

    return {
        "ok": True,
        "filename": filename,
        "coverAdded": cover_added,
        "coverImage": current.get("coverImage"),
        "url": template_store._chub_url_from_card(normalized),
    }


@router.delete("/{template_id}/sources/{filename}")
async def delete_template_source(template_id: str, filename: str):
    if not template_store.delete_source(template_id, filename):
        raise HTTPException(404, "Source not found")
    return {"ok": True}


# ── Rerun & Enrich (SSE — long-running LLM ops with heartbeats) ──

def _load_settings(preset_id: str) -> dict:
    from app.config import DATA_DIR
    path = DATA_DIR / "presets" / "settings" / f"{preset_id}.json"
    if not path.is_file():
        path = DATA_DIR / "presets" / "settings" / "default.json"
    return json.loads(path.read_text(encoding="utf-8"))


async def _template_op_runner(
    job, template_id: str, source_filename: str, action: str,
    llm_fn, card: dict, current: dict, settings: dict,
):
    """Job runner shared by rerun + enrich. Ensures the model is loaded,
    streams LLM events to the job, then saves the new version to disk."""
    from app.services import llm_process
    # External providers (xai, openai, ...) don't need llama-server running.
    if settings.get("provider", "llama-server") == "llama-server" and not llm_process.is_running():
        job.emit({"type": "model_loading", "modelPath": settings.get("modelPath")})
        try:
            await llm_process.ensure_loaded(settings)
        except (RuntimeError, TimeoutError) as e:
            raise RuntimeError(str(e))
        job.emit({"type": "model_loaded"})

    job.emit({"type": "started", "action": action})
    log.info("[%s job %s] starting LLM call against %s", action, job.id[:8], template_id)

    new_body = await llm_fn(card, current, settings, job=job)
    log.info("[%s job %s] LLM returned, parsing + saving new version", action, job.id[:8])

    if current.get("coverImage"):
        new_body["coverImage"] = current["coverImage"]
    saved, new_version = template_store.add_version(
        template_id, new_body, action=action, source_ref=source_filename,
    )
    log.info("[%s job %s] saved %s as version %s", action, job.id[:8], template_id, new_version)

    job.set_result({
        "template": saved,
        "version": new_version,
        "sourceFilename": source_filename,
        "action": action,
    })
    job.emit({
        "type": "done",
        "template": saved,
        "version": new_version,
        "sourceFilename": source_filename,
        "action": action,
    })


def _create_template_op_job(
    template_id: str, source_filename: str, preset_id: str,
    action: str, llm_fn,
) -> dict:
    """Validate inputs, create the job, return `{jobId}` immediately.
    Caller (rerun/enrich endpoint) returns this as plain JSON — no SSE.
    The toast bar's existing /api/jobs/stream picks up the new job and
    shows progress; the modal that triggered the action just closes."""
    card = template_store.load_source(template_id, source_filename)
    if card is None:
        raise HTTPException(404, f"Source '{source_filename}' not found")
    current = template_store.load_current(template_id)
    if current is None:
        raise HTTPException(404, "Template not found")
    try:
        settings = _load_settings(preset_id)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(500, f"Could not load preset '{preset_id}': {e}")

    label = f"{action.capitalize()} · {template_id}"
    job = job_manager.create_job(
        kind=action,
        label=label,
        runner=lambda j: _template_op_runner(
            j, template_id, source_filename, action, llm_fn, card, current, settings
        ),
    )
    return {"jobId": job.id, "kind": action, "templateId": template_id}


@router.post("/{template_id}/rerun")
async def rerun_template_analysis(template_id: str, body: dict):
    """Re-analyze the same source against the current template (audit/correct/fill).
    Returns {jobId} immediately — the actual work runs as a background job
    visible in /api/jobs and the toast bar. Survives client disconnect
    (the new version lands on disk regardless)."""
    from app.routers.presets import find_default_preset_id
    source_filename = body.get("sourceFilename")
    preset_arg = body.get("settingsPresetId")
    preset_id = preset_arg if (preset_arg and preset_arg != "default") else find_default_preset_id()
    if not source_filename:
        raise HTTPException(400, "sourceFilename is required")
    from app.services.chub_importer import rerun_with_current
    return _create_template_op_job(
        template_id, source_filename, preset_id, "rerun", rerun_with_current,
    )


@router.post("/{template_id}/enrich")
async def enrich_template(template_id: str, body: dict):
    """Merge a NEW card into the current template (different character, same
    universe). Returns {jobId} immediately, same as /rerun."""
    from app.routers.presets import find_default_preset_id
    source_filename = body.get("sourceFilename")
    preset_arg = body.get("settingsPresetId")
    preset_id = preset_arg if (preset_arg and preset_arg != "default") else find_default_preset_id()
    if not source_filename:
        raise HTTPException(400, "sourceFilename is required")
    from app.services.chub_importer import enrich_with_new_card
    return _create_template_op_job(
        template_id, source_filename, preset_id, "enrich", enrich_with_new_card,
    )


# ── Ask the Template ──────────────────────────────────────────────────────
# Meta-analytical Q&A scoped to the template (not to a session). Optionally
# attach a session as evidence so the model can cross-reference what the
# template ASKS for vs what it ACTUALLY produces.

async def _template_query_pipeline(job, messages: list[dict], settings: dict, template_id: str, query_id: int):
    """Stream the consultant LLM, persist the result to `template_queries`."""
    from datetime import datetime, timezone
    from app.database import get_db
    from app.services.llm_stream import stream_query

    db = await get_db()
    thinking_parts: list[str] = []
    answer_parts: list[str] = []
    final_thinking = ""
    final_answer = ""
    final_model = ""
    try:
        async for ev in stream_query(
            messages,
            temperature=settings.get("temperature"),
            max_tokens=settings.get("maxTokens", 4096),
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            seed=settings.get("seed"),
            session_id=None,
            settings=settings,
        ):
            t = ev.get("type")
            if t == "thinking_chunk":
                thinking_parts.append(ev.get("text", ""))
            elif t == "answer_chunk":
                answer_parts.append(ev.get("text", ""))
            elif t == "done":
                result = ev.get("result") or {}
                final_thinking = result.get("thinking") or "".join(thinking_parts)
                final_answer = result.get("answer") or "".join(answer_parts)
                final_model = result.get("modelName", "") or ""
            elif t == "error":
                raise RuntimeError(ev.get("message") or "stream error")
            job.emit(ev)

        completed_at = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE template_queries SET thinking = ?, answer = ?, status = ?, model = ?, completed_at = ? WHERE id = ?",
            (final_thinking, final_answer, "success", final_model, completed_at, query_id),
        )
        await db.commit()
    except asyncio.CancelledError:
        completed_at = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE template_queries SET thinking = ?, answer = ?, status = ?, completed_at = ? WHERE id = ?",
            ("".join(thinking_parts), "".join(answer_parts), "cancelled", completed_at, query_id),
        )
        await db.commit()
        job.emit({"type": "error", "message": "cancelled"})
        raise
    except Exception as e:
        log.exception("Template query pipeline failed")
        completed_at = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE template_queries SET thinking = ?, answer = ?, status = ?, error = ?, completed_at = ? WHERE id = ?",
            ("".join(thinking_parts), "".join(answer_parts), "error", str(e), completed_at, query_id),
        )
        await db.commit()
        job.emit({"type": "error", "message": str(e)})


@router.post("/{template_id}/query/stream")
async def template_query_streaming(template_id: str, body: dict):
    """Ask-the-Template: meta-analytical Q&A streamed as SSE.

    Body:
      {
        "question": str,
        "sessionId": str | null   // if set, attach the session's recent
                                  // chunks + asks as evidence
      }
    """
    from datetime import datetime, timezone
    from app.database import get_db
    from app.services.prompts import build_template_query_messages
    from app.routers.presets import find_default_preset_id
    from app.services import job_manager
    from app.config import DATA_DIR

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question is required")

    template = template_store.load_current(template_id)
    if template is None:
        raise HTTPException(404, f"Template '{template_id}' not found")
    template_version = template_store.current_version(template_id)

    # Settings: prefer the session's preset if a session is attached, else
    # fall back to the default preset. Templates have no preset of their own.
    db = await get_db()
    session_id = body.get("sessionId")
    preset_id = None
    if session_id:
        sess_row = await db.execute_fetchall(
            "SELECT settings_preset_id FROM sessions WHERE id = ?", (session_id,)
        )
        if sess_row:
            preset_id = sess_row[0][0]
    eff_id = preset_id if (preset_id and preset_id != "default") else find_default_preset_id()
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{eff_id}.json").read_text(encoding="utf-8"))

    # Past asks for THIS template — provides Q&A continuity so a follow-up
    # like "and what about X?" works.
    history_rows = await db.execute_fetchall(
        "SELECT question, answer FROM template_queries WHERE template_id = ? AND status = 'success' ORDER BY id ASC",
        (template_id,),
    )
    history = [{"question": r[0], "answer": r[1]} for r in history_rows]

    # Optional session evidence — recent chunks + the user's prior in-story
    # asks. The model cross-references "what the template asks for" against
    # "what it actually produced" to identify under-specification.
    session_context = None
    if session_id:
        sess_row = await db.execute_fetchall(
            "SELECT title FROM sessions WHERE id = ?", (session_id,)
        )
        if sess_row:
            n_recent = max(2, int(settings.get("chunkUpdateInterval", 10)))
            chunk_rows = await db.execute_fetchall(
                '''SELECT c.id, c.chapter_id, c."order", c.active_version, c.versions
                   FROM chunks c
                   JOIN chapters ch ON c.chapter_id = ch.id
                   WHERE c.session_id = ?
                   ORDER BY ch."order" DESC, c."order" DESC
                   LIMIT ?''',
                (session_id, n_recent),
            )
            recent_chunks = [
                {"id": r[0], "chapterId": r[1], "order": r[2], "active_version": r[3], "versions": r[4]}
                for r in reversed(chunk_rows)
            ]
            ask_rows = await db.execute_fetchall(
                "SELECT question, answer FROM session_queries WHERE session_id = ? AND status = 'success' ORDER BY id ASC",
                (session_id,),
            )
            session_asks = [{"question": r[0], "answer": r[1]} for r in ask_rows]
            session_context = {
                "session_id": session_id,
                "session_title": sess_row[0][0],
                "recent_chunks": recent_chunks,
                "session_asks": session_asks,
            }

    messages = build_template_query_messages(
        question=question,
        template=template,
        settings=settings,
        history=history,
        session_context=session_context,
    )

    created_at = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "INSERT INTO template_queries (template_id, template_version, session_id, question, status, created_at) "
        "VALUES (?, ?, ?, ?, 'running', ?)",
        (template_id, template_version, session_id, question, created_at),
    )
    query_id = cursor.lastrowid
    await db.commit()

    job = job_manager.create_job(
        kind="template-query",
        label=f"Ask Template · {question[:60]}{'…' if len(question) > 60 else ''}",
        session_id=None,
        runner=lambda j: _template_query_pipeline(j, messages, settings, template_id, query_id),
    )

    from app.routers.generate import _relay_queue_to_sse  # reuse existing SSE relay
    return StreamingResponse(
        _relay_queue_to_sse(job.subscribe()),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/{template_id}/queries")
async def list_template_queries(template_id: str):
    """Return every Ask-the-Template entry for this template, oldest first.
    The modal loads this on mount so Q&A history persists across open/close,
    page reloads, and devices."""
    from app.database import get_db
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id, template_version, session_id, question, thinking, answer, status, error, model, created_at, completed_at "
        "FROM template_queries WHERE template_id = ? ORDER BY id ASC",
        (template_id,),
    )
    return {
        "queries": [
            {
                "id": r[0], "templateVersion": r[1], "sessionId": r[2],
                "question": r[3], "thinking": r[4], "answer": r[5],
                "status": r[6], "error": r[7], "model": r[8],
                "createdAt": r[9], "completedAt": r[10],
            }
            for r in rows
        ]
    }


# ── Rewrite Template ──────────────────────────────────────────────────────
# LLM-driven rewrite that takes the current template + a feedback comment +
# optionally selected meta-analytical asks, and writes a new version with
# the same schema. The user never sees the JSON in the modal — only the
# feedback textarea + checkboxes for asks. Output lands as a new numbered
# version (existing `add_version` mechanism).

# Required top-level fields the LLM output must include for the rewrite to
# be accepted. We don't validate inner shapes (the model is trusted to keep
# fidelity — the prompt is strict). Missing top-levels = reject.
_REWRITE_REQUIRED_FIELDS = (
    "name", "description", "variables", "characters", "scenario",
    "maskedIntents", "milestones", "systemPromptAdditions",
)


async def _template_rewrite_pipeline(job, messages: list[dict], settings: dict, template_id: str, original: dict, feedback: str):
    """Stream the rewriter LLM, parse the full template JSON, save as a new
    version. Emits structured events so the UI can show progress without
    rendering the JSON itself.
    """
    from app.services.llm_stream import _StructuredParser  # noqa
    from app.services.llm import run_llm_stream
    from app.services.prompts import effective_prompt  # noqa

    full_buffer: list[str] = []
    model_name = ""
    try:
        async for ev in run_llm_stream(
            messages,
            settings=settings,
            kind="template-rewrite",
            session_id=None,
            temperature=settings.get("temperature"),
            max_tokens=(settings.get("thinkingTokens", 1500) + 4000),
            top_p=settings.get("topP"),
            top_k=settings.get("topK"),
            seed=settings.get("seed"),
        ):
            t = ev.get("type")
            if t == "delta":
                full_buffer.append(ev["text"])
                # Forward a coarse-grained progress signal — the UI shows
                # token count from the activity tracker, so a single
                # 'progress' tick per delta is enough here.
                job.emit({"type": "progress", "chars": sum(len(x) for x in full_buffer)})
            elif t == "model":
                model_name = ev["name"]
                job.emit(ev)
            elif t == "thinking_delta":
                # Don't forward thinking text to the client (we don't render
                # it for rewrite), but keep the event type so the toast
                # progress UI knows we're still alive.
                job.emit({"type": "thinking_progress", "chars": len(ev.get("text", ""))})
            elif t in ("started", "usage", "first_token"):
                job.emit(ev)
            # Skip llm_done — handled below via full_buffer parse.

        raw = "".join(full_buffer)
        try:
            new_template = json.loads(raw)
        except json.JSONDecodeError as e:
            job.emit({"type": "error", "message": f"Model returned invalid JSON: {e.msg}"})
            return

        missing = [f for f in _REWRITE_REQUIRED_FIELDS if f not in new_template]
        if missing:
            job.emit({
                "type": "error",
                "message": f"Rewritten template is missing required fields: {', '.join(missing)}. Try again with clearer feedback.",
            })
            return

        # Force identity fields back to the original — the prompt asks the
        # model to echo them verbatim, but we enforce defensively.
        new_template["id"] = template_id
        if original.get("coverImage"):
            new_template["coverImage"] = original["coverImage"]

        try:
            saved_body, version = template_store.add_version(
                template_id, new_template,
                action="llm-rewrite",
            )
        except Exception as e:
            log.exception("Failed to save rewritten template")
            job.emit({"type": "error", "message": f"Could not save new version: {e}"})
            return

        job.set_result({
            "version": version,
            "modelName": model_name,
            "feedbackPreview": feedback[:200],
        })
        job.emit({
            "type": "done",
            "kind": "template-rewrite",
            "version": version,
            "templateId": template_id,
        })
    except asyncio.CancelledError:
        job.emit({"type": "error", "message": "cancelled"})
        raise
    except Exception as e:
        log.exception("Template rewrite pipeline failed")
        job.emit({"type": "error", "message": str(e)})


@router.post("/{template_id}/rewrite")
async def rewrite_template(template_id: str, body: dict):
    """Rewrite this template using LLM, guided by the user's feedback and
    optionally a selection of meta-analytical asks.

    Body:
      {
        "feedback": str,             # required: what to change
        "askIds": [int, ...] | null  # optional: template_queries.id list
      }

    Returns SSE stream. The new version is saved automatically; the `done`
    event includes its number (e.g. "0002").
    """
    from datetime import datetime, timezone  # noqa
    from app.database import get_db
    from app.services.prompts import build_template_rewrite_messages
    from app.routers.presets import find_default_preset_id
    from app.services import job_manager
    from app.config import DATA_DIR

    feedback = (body.get("feedback") or "").strip()
    if not feedback:
        raise HTTPException(400, "feedback is required (describe what to change)")
    ask_ids = body.get("askIds") or []
    if not isinstance(ask_ids, list) or not all(isinstance(x, int) for x in ask_ids):
        raise HTTPException(400, "askIds must be a list of integers")

    template = template_store.load_current(template_id)
    if template is None:
        raise HTTPException(404, f"Template '{template_id}' not found")

    eff_id = find_default_preset_id()
    settings = json.loads((DATA_DIR / "presets" / "settings" / f"{eff_id}.json").read_text(encoding="utf-8"))

    selected_asks: list[dict] = []
    if ask_ids:
        db = await get_db()
        # Use parameterized IN clause — build the placeholder string explicitly
        # rather than relying on string formatting on user input.
        placeholders = ",".join("?" for _ in ask_ids)
        rows = await db.execute_fetchall(
            f"SELECT id, question, answer FROM template_queries "
            f"WHERE template_id = ? AND id IN ({placeholders}) AND status = 'success'",
            (template_id, *ask_ids),
        )
        selected_asks = [{"id": r[0], "question": r[1], "answer": r[2]} for r in rows]

    messages = build_template_rewrite_messages(
        template=template,
        feedback=feedback,
        selected_asks=selected_asks,
        settings=settings,
    )

    job = job_manager.create_job(
        kind="template-rewrite",
        label=f"Rewrite template · {template_id[:30]}",
        session_id=None,
        runner=lambda j: _template_rewrite_pipeline(j, messages, settings, template_id, template, feedback),
    )

    from app.routers.generate import _relay_queue_to_sse
    return StreamingResponse(
        _relay_queue_to_sse(job.subscribe()),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
