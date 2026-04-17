"""Settings presets CRUD — stays as JSON files for easy hand-editing."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.config import DATA_DIR

router = APIRouter()

SETTINGS_PATH = DATA_DIR / "presets" / "settings"


def _ensure_dir():
    SETTINGS_PATH.mkdir(parents=True, exist_ok=True)


@router.get("/")
async def list_presets():
    _ensure_dir()
    result = []
    for f in sorted(SETTINGS_PATH.glob("*.json")):
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return result


@router.get("/{preset_id}")
async def get_preset(preset_id: str):
    path = SETTINGS_PATH / f"{preset_id}.json"
    if not path.is_file():
        raise HTTPException(404, f"Preset '{preset_id}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/")
async def save_preset(body: dict):
    _ensure_dir()
    pid = body.get("id")
    if not pid:
        raise HTTPException(400, "Preset id is required")
    path = SETTINGS_PATH / f"{pid}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return body


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str):
    if preset_id == "default":
        raise HTTPException(400, "Cannot delete the default preset")
    path = SETTINGS_PATH / f"{preset_id}.json"
    if path.is_file():
        path.unlink()
    return {"ok": True}
