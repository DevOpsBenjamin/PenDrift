"""Import routes — convert external character cards to PenDrift templates."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.services.chub_importer import fetch_chub_card, convert_card_to_template, _normalize_card
from app.config import DATA_DIR

router = APIRouter()

TEMPLATES_PATH = DATA_DIR / "presets" / "templates"


def _load_settings(preset_id: str = "default") -> dict:
    path = DATA_DIR / "presets" / "settings" / f"{preset_id}.json"
    if not path.is_file():
        path = DATA_DIR / "presets" / "settings" / "default.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/chub")
async def import_from_chub(body: dict):
    """Import a character card from chub.ai URL or raw JSON and convert to PenDrift template.

    Body:
    - url: chub.ai character URL
    - card: raw V2 character card JSON (alternative to url)
    - save: also save as template file (default: false, just preview)
    - settingsPresetId: which preset to read the import prompt from (default: "default")
    """
    url = body.get("url")
    raw_card = body.get("card")
    save = body.get("save", False)
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

    # Step 2: Convert via LLM
    try:
        template = await convert_card_to_template(card, settings)
    except Exception as e:
        raise HTTPException(502, f"LLM conversion failed: {e}")

    # Step 3: Optionally save
    if save:
        TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)
        path = TEMPLATES_PATH / f"{template['id']}.json"
        path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
        template["_saved"] = True

    return {
        "template": template,
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
