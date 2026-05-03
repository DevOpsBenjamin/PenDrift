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

    new_body = await llm_fn(card, current, settings, job=job)
    if current.get("coverImage"):
        new_body["coverImage"] = current["coverImage"]
    saved, new_version = template_store.add_version(
        template_id, new_body, action=action, source_ref=source_filename,
    )

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


async def _stream_llm_op(template_id: str, source_filename: str, preset_id: str,
                         action: str, llm_fn):
    """SSE generator for rerun + enrich. Creates a job and relays its event
    stream so the existing client SSE contract (open / model_loading /
    started / done / error events) keeps working — and so the same op also
    shows up in /api/jobs and the Activity view."""
    yield ": stream open\n\n"

    card = template_store.load_source(template_id, source_filename)
    if card is None:
        yield _sse({"type": "error", "message": f"Source '{source_filename}' not found"})
        return
    current = template_store.load_current(template_id)
    if current is None:
        yield _sse({"type": "error", "message": "Template not found"})
        return
    try:
        settings = _load_settings(preset_id)
    except (json.JSONDecodeError, OSError) as e:
        yield _sse({"type": "error", "message": f"Could not load preset '{preset_id}': {e}"})
        return

    label = f"{action.capitalize()} · {template_id}"
    job = job_manager.create_job(
        kind=action,
        label=label,
        runner=lambda j: _template_op_runner(
            j, template_id, source_filename, action, llm_fn, card, current, settings
        ),
    )

    queue = job.subscribe()
    while True:
        try:
            ev = await queue.get()
        except asyncio.CancelledError:
            log.info("SSE %s for %s: client disconnected, job continues", action, template_id)
            raise
        if ev is None:
            # Job finalized. If it failed and never emitted an error event,
            # surface the stored error so the client doesn't hang on `done`.
            if job.status == "error" and not any(e.get("type") == "error" for e in job.events):
                yield _sse({"type": "error", "message": f"LLM {action} failed: {job.error}"})
            return
        yield _sse(ev)


@router.post("/{template_id}/rerun")
async def rerun_template_analysis(template_id: str, body: dict):
    """Re-analyze the same source against the current template (audit/correct/fill).
    SSE response — emits processing heartbeats then a `done` event when the new
    version is saved. Survives client disconnect (the new version still lands
    on disk and shows up in History)."""
    from app.routers.presets import find_default_preset_id
    source_filename = body.get("sourceFilename")
    preset_arg = body.get("settingsPresetId")
    preset_id = preset_arg if (preset_arg and preset_arg != "default") else find_default_preset_id()
    if not source_filename:
        raise HTTPException(400, "sourceFilename is required")
    from app.services.chub_importer import rerun_with_current
    return StreamingResponse(
        _stream_llm_op(template_id, source_filename, preset_id, "rerun", rerun_with_current),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/{template_id}/enrich")
async def enrich_template(template_id: str, body: dict):
    """Merge a NEW card into the current template (different character, same
    universe). SSE response, same shape as rerun."""
    from app.routers.presets import find_default_preset_id
    source_filename = body.get("sourceFilename")
    preset_arg = body.get("settingsPresetId")
    preset_id = preset_arg if (preset_arg and preset_arg != "default") else find_default_preset_id()
    if not source_filename:
        raise HTTPException(400, "sourceFilename is required")
    from app.services.chub_importer import enrich_with_new_card
    return StreamingResponse(
        _stream_llm_op(template_id, source_filename, preset_id, "enrich", enrich_with_new_card),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
