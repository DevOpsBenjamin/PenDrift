"""Import routes — convert external character cards to PenDrift templates."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.services.chub_importer import fetch_chub_card, convert_card_to_template, _normalize_card, download_card_avatar
from app.services import template_store, llm_process, job_manager
from app.services.job_manager import Job
from app.config import DATA_DIR

router = APIRouter()


def _load_settings(preset_id: str = "default") -> dict:
    path = DATA_DIR / "presets" / "settings" / f"{preset_id}.json"
    if not path.is_file():
        path = DATA_DIR / "presets" / "settings" / "default.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _build_card_summary(card: dict) -> dict:
    return {
        "name": card.get("name"),
        "tags": card.get("tags", []),
        "hasFirstMessage": bool(card.get("first_mes")),
        "hasExamples": bool(card.get("mes_example")),
        "hasAlternateGreetings": len(card.get("alternate_greetings", [])),
        "descriptionLength": len(card.get("description", "")),
    }


async def _import_runner(job: Job, card: dict, settings: dict, url: str | None) -> None:
    """Job runner that converts a card → template → saves to disk → fetches
    avatar. Emits phase + LLM events for the toast bar."""
    job.emit({"type": "phase", "name": "ensure_model"})
    try:
        await llm_process.ensure_loaded(settings)
    except RuntimeError as e:
        raise RuntimeError(str(e))
    except TimeoutError as e:
        raise RuntimeError(f"llama-server failed to start: {e}")

    job.emit({"type": "phase", "name": "convert"})
    template = await convert_card_to_template(card, settings, job=job)

    job.emit({"type": "phase", "name": "save"})
    try:
        template_store.create_new_template(
            template["id"], template, action="import",
            source_url=url, source_json=card,
        )
    except ValueError as e:
        raise ValueError(str(e))

    avatar = await download_card_avatar(card)
    if avatar:
        content, ext = avatar
        try:
            filename = template_store.write_image(template["id"], content, ext)
            template["coverImage"] = filename
            template_store.save_in_place(template["id"], template)
        except (ValueError, OSError):
            pass

    job.set_result({
        "template": template,
        "saved": True,
        "originalCard": _build_card_summary(card),
    })
    job.emit({"type": "phase", "name": "done"})


@router.post("/chub")
async def import_from_chub(body: dict):
    """Import a character card from chub.ai URL or raw JSON and convert to a
    PenDrift template. The result is ALWAYS saved as a new folder with
    `0001.json` + `sources/0001-card.json` + avatar (if found).

    Runs as a background job (visible in /api/jobs and the Activity view).
    The HTTP request stays open until the job finishes — but the job
    survives client disconnect, so a refresh during a long import still
    leaves the template on disk.

    Body:
    - url: chub.ai character URL
    - card: raw V2 character card JSON (alternative to url)
    - settingsPresetId: which preset to read the import prompt from (default: "default")
    """
    url = body.get("url")
    raw_card = body.get("card")
    preset_id = body.get("settingsPresetId", "default")

    if not url and not raw_card:
        raise HTTPException(400, "Provide 'url' (chub.ai link) or 'card' (raw JSON)")

    settings = _load_settings(preset_id)

    try:
        if raw_card:
            card = _normalize_card(raw_card) if isinstance(raw_card, dict) else _normalize_card(json.loads(raw_card))
        else:
            card = await fetch_chub_card(url)
    except Exception as e:
        raise HTTPException(400, f"Could not fetch/parse card: {e}")

    label = f"Import · {card.get('name') or url or 'card'}"
    job = await job_manager.run_and_wait(
        kind="chub-import",
        label=label,
        runner=lambda j: _import_runner(j, card, settings, url),
    )
    if job.status == "cancelled":
        raise HTTPException(499, "Import cancelled")
    if job.status == "error":
        raise HTTPException(502, f"Import failed: {job.error}")
    return {**(job.result or {}), "jobId": job.id}


@router.post("/card-json")
async def import_from_json_upload(body: dict):
    """Import from a raw character card JSON (pasted or uploaded). Same
    background-job semantics as /chub but takes raw JSON only (no URL fetch
    and no save to disk — the caller decides what to do with the template)."""
    card_data = body.get("card")
    if not card_data:
        raise HTTPException(400, "Provide 'card' with the character card JSON")

    preset_id = body.get("settingsPresetId", "default")
    settings = _load_settings(preset_id)

    card = _normalize_card(card_data) if isinstance(card_data, dict) else _normalize_card(json.loads(card_data))

    async def _runner(j: Job):
        j.emit({"type": "phase", "name": "ensure_model"})
        try:
            await llm_process.ensure_loaded(settings)
        except (RuntimeError, TimeoutError) as e:
            raise RuntimeError(str(e))
        j.emit({"type": "phase", "name": "convert"})
        template = await convert_card_to_template(card, settings, job=j)
        j.set_result({"template": template})
        j.emit({"type": "phase", "name": "done"})

    label = f"Import (JSON) · {card.get('name') or 'card'}"
    job = await job_manager.run_and_wait(
        kind="chub-import",
        label=label,
        runner=_runner,
    )
    if job.status == "cancelled":
        raise HTTPException(499, "Import cancelled")
    if job.status == "error":
        raise HTTPException(502, f"Import failed: {job.error}")
    return {**(job.result or {}), "jobId": job.id}
