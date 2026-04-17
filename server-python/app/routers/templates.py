"""Template CRUD routes — stays as JSON files for easy hand-editing."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.config import DATA_DIR

router = APIRouter()

TEMPLATES_PATH = DATA_DIR / "presets" / "templates"


def _ensure_dir():
    TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)


@router.get("/")
async def list_templates():
    _ensure_dir()
    result = []
    for f in sorted(TEMPLATES_PATH.glob("*.json")):
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return result


@router.get("/{template_id}")
async def get_template(template_id: str):
    path = TEMPLATES_PATH / f"{template_id}.json"
    if not path.is_file():
        raise HTTPException(404, f"Template '{template_id}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/")
async def save_template(body: dict):
    _ensure_dir()
    tid = body.get("id")
    if not tid:
        raise HTTPException(400, "Template id is required")
    path = TEMPLATES_PATH / f"{tid}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return body


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    path = TEMPLATES_PATH / f"{template_id}.json"
    if path.is_file():
        path.unlink()
    return {"ok": True}
