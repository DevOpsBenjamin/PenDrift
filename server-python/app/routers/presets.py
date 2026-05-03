"""Settings presets CRUD — stays as JSON files for easy hand-editing.
Merges built-in defaults with user-defined presets in DATA_DIR.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import DATA_DIR, DEFAULTS_DIR

log = logging.getLogger("pendrift.presets")
router = APIRouter()

USER_SETTINGS_PATH = DATA_DIR / "presets" / "settings"
DEFAULT_SETTINGS_PATH = DEFAULTS_DIR / "settings"


def _ensure_dir():
    USER_SETTINGS_PATH.mkdir(parents=True, exist_ok=True)


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        # Ensure the preset has an ID based on its filename if missing
        if "id" not in data:
            data["id"] = path.stem
        return data
    except (json.JSONDecodeError, OSError):
        return None


@router.get("")
async def list_presets():
    _ensure_dir()
    presets = {}

    # 1. Load built-in defaults
    if DEFAULT_SETTINGS_PATH.is_dir():
        for f in DEFAULT_SETTINGS_PATH.glob("*.json"):
            data = _read(f)
            if data:
                presets[data["id"]] = data

    # 2. Load user presets (overwriting defaults if same ID)
    if USER_SETTINGS_PATH.is_dir():
        for f in USER_SETTINGS_PATH.glob("*.json"):
            data = _read(f)
            if data:
                presets[data["id"]] = data

    return sorted(list(presets.values()), key=lambda x: x.get("name", "").lower())


@router.get("/{preset_id}")
async def get_preset(preset_id: str):
    # Try user first, then default
    path = USER_SETTINGS_PATH / f"{preset_id}.json"
    if not path.is_file():
        path = DEFAULT_SETTINGS_PATH / f"{preset_id}.json"

    if not path.is_file():
        raise HTTPException(404, f"Preset '{preset_id}' not found")

    data = _read(path)
    if data is None:
        raise HTTPException(500, f"Failed to read preset '{preset_id}'")
    return data


@router.post("")
async def save_preset(body: dict):
    _ensure_dir()
    pid = body.get("id")
    if not pid:
        raise HTTPException(400, "Preset id is required")

    # When saving, we always save to the user directory
    path = USER_SETTINGS_PATH / f"{pid}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return body


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str):
    if preset_id == "default":
        raise HTTPException(400, "Cannot delete the default preset")

    # Only user presets can be deleted. Defaults are immutable.
    path = USER_SETTINGS_PATH / f"{preset_id}.json"
    if path.is_file():
        path.unlink()
        return {"ok": True}

    if (DEFAULT_SETTINGS_PATH / f"{preset_id}.json").is_file():
        raise HTTPException(400, "Built-in presets cannot be deleted")

    raise HTTPException(404, f"Preset '{preset_id}' not found")


@router.post("/{preset_id}/make-default")
async def make_default_preset(preset_id: str):
    """Mark this preset as the user's default. Clears `isDefault` from every
    other preset so exactly one is flagged at a time."""
    _ensure_dir()

    # Find the target preset (user or default)
    target_data = None
    all_preset_ids = set()

    # Get all potential preset IDs
    for p in [USER_SETTINGS_PATH, DEFAULT_SETTINGS_PATH]:
        if p.is_dir():
            for f in p.glob("*.json"):
                all_preset_ids.add(f.stem)

    if preset_id not in all_preset_ids:
        raise HTTPException(404, f"Preset '{preset_id}' not found")

    # Iterate over all user presets to clear the flag, and also handle the target
    for pid in all_preset_ids:
        # We only ever write to USER_SETTINGS_PATH
        user_file = USER_SETTINGS_PATH / f"{pid}.json"

        # If it's the target, we must ensure it exists in USER path and has the flag
        if pid == preset_id:
            # Load from where it exists
            src_path = user_file if user_file.is_file() else (DEFAULT_SETTINGS_PATH / f"{pid}.json")
            data = _read(src_path)
            if data:
                data["isDefault"] = True
                user_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            # If it's NOT the target, if it exists in USER path and has the flag, remove it
            if user_file.is_file():
                data = _read(user_file)
                if data and data.get("isDefault"):
                    data.pop("isDefault", None)
                    user_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"ok": True, "defaultPresetId": preset_id}


def find_default_preset_id() -> str:
    """Return the id of the preset flagged isDefault=True, or 'default' if
    none flagged. Checks user presets first, then defaults."""
    # Check user presets for the flag
    if USER_SETTINGS_PATH.is_dir():
        for f in USER_SETTINGS_PATH.glob("*.json"):
            data = _read(f)
            if data and data.get("isDefault"):
                return data.get("id") or f.stem

    # Check defaults as a fallback (though typically they don't have isDefault=True)
    if DEFAULT_SETTINGS_PATH.is_dir():
        for f in DEFAULT_SETTINGS_PATH.glob("*.json"):
            data = _read(f)
            if data and data.get("isDefault"):
                return data.get("id") or f.stem

    return "default"
