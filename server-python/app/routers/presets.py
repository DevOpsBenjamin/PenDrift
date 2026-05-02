"""Settings presets CRUD — stays as JSON files for easy hand-editing."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.config import DATA_DIR

router = APIRouter()

SETTINGS_PATH = DATA_DIR / "presets" / "settings"


def _ensure_dir():
    SETTINGS_PATH.mkdir(parents=True, exist_ok=True)


@router.get("")
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


@router.post("")
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


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@router.post("/{preset_id}/make-default")
async def make_default_preset(preset_id: str):
    """Mark this preset as the user's default. Clears `isDefault` from every
    other preset so exactly one is flagged at a time."""
    _ensure_dir()
    target_path = SETTINGS_PATH / f"{preset_id}.json"
    if not target_path.is_file():
        raise HTTPException(404, f"Preset '{preset_id}' not found")
    for f in SETTINGS_PATH.glob("*.json"):
        data = _read(f)
        if data is None:
            continue
        is_target = f.name == f"{preset_id}.json"
        # Set isDefault only on the target; clear on all others
        if is_target and not data.get("isDefault"):
            data["isDefault"] = True
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif not is_target and data.get("isDefault"):
            data.pop("isDefault", None)
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "defaultPresetId": preset_id}


def find_default_preset_id() -> str:
    """Return the id of the preset flagged isDefault=True, or 'default' if
    none flagged. Used by operations that don't have a session context."""
    _ensure_dir()
    for f in SETTINGS_PATH.glob("*.json"):
        data = _read(f)
        if data is not None and data.get("isDefault"):
            return data.get("id") or f.stem
    return "default"
