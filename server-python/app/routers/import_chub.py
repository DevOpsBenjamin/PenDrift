"""Import routes — convert external character cards to PenDrift templates."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.services.chub_importer import fetch_chub_card, convert_card_to_template, _normalize_card, download_card_avatar
from app.services import template_store, llm_process
from app.config import DATA_DIR

router = APIRouter()


def _load_settings(preset_id: str = "default") -> dict:
    path = DATA_DIR / "presets" / "settings" / f"{preset_id}.json"
    if not path.is_file():
        path = DATA_DIR / "presets" / "settings" / "default.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/chub")
async def import_from_chub(body: dict):
    """Import a character card from chub.ai URL or raw JSON and convert to a
    PenDrift template. The result is ALWAYS saved as a new folder with
    `0001.json` + `sources/0001-card.json` + avatar (if found).

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

    # Step 1: Get the card data
    try:
        if raw_card:
            card = _normalize_card(raw_card) if isinstance(raw_card, dict) else _normalize_card(json.loads(raw_card))
        else:
            card = await fetch_chub_card(url)
    except Exception as e:
        raise HTTPException(400, f"Could not fetch/parse card: {e}")

    # Step 1.5: Make sure llama-server is up (auto-load with this preset)
    try:
        await llm_process.ensure_loaded(settings)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except (TimeoutError,) as e:
        raise HTTPException(503, f"llama-server failed to start: {e}")

    # Step 2: Convert via LLM
    try:
        template = await convert_card_to_template(card, settings)
    except Exception as e:
        raise HTTPException(502, f"LLM conversion failed: {e}")

    # Step 3: Save the folder + initial version + source
    try:
        template_store.create_new_template(
            template["id"],
            template,
            action="import",
            source_url=url if url else None,
            source_json=card,
        )
    except ValueError as e:
        # Template id already exists — caller can fix the id and retry, or
        # delete the existing one first.
        raise HTTPException(409, str(e))

    # Step 4: Best-effort avatar download → write into the template folder
    avatar = await download_card_avatar(card)
    if avatar:
        content, ext = avatar
        try:
            filename = template_store.write_image(template["id"], content, ext)
            template["coverImage"] = filename
            # Persist the coverImage update on the just-created version
            template_store.save_in_place(template["id"], template)
        except (ValueError, OSError):
            pass

    return {
        "template": template,
        "saved": True,
        "originalCard": {
            "name": card.get("name"),
            "tags": card.get("tags", []),
            "hasFirstMessage": bool(card.get("first_mes")),
            "hasExamples": bool(card.get("mes_example")),
            "hasAlternateGreetings": len(card.get("alternate_greetings", [])),
            "descriptionLength": len(card.get("description", "")),
        },
    }


@router.post("/card-json")
async def import_from_json_upload(body: dict):
    """Import from a raw character card JSON (pasted or uploaded)."""
    card_data = body.get("card")
    if not card_data:
        raise HTTPException(400, "Provide 'card' with the character card JSON")

    preset_id = body.get("settingsPresetId", "default")
    settings = _load_settings(preset_id)

    card = _normalize_card(card_data) if isinstance(card_data, dict) else _normalize_card(json.loads(card_data))

    try:
        template = await convert_card_to_template(card, settings)
    except Exception as e:
        raise HTTPException(502, f"LLM conversion failed: {e}")

    return {"template": template}
