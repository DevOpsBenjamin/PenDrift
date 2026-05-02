"""Bundled prompt registry — system prompts ship with the app code.

Prompts are loaded from `app/prompts/*.md` at startup. Settings presets can
optionally override a prompt by setting the corresponding `<name>Prompt` field
to a non-null string. When the override is null/missing/empty, the bundled
default is used.

Add a new prompt:
1. Drop a new `<name>.md` file under `app/prompts/`
2. Reference it as `effective_prompt("<name>", settings)` from your service
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR

log = logging.getLogger("pendrift.prompts")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_cache: dict[str, str] = {}


def _load() -> None:
    """Read every .md file under prompts/ into the cache. Called lazily."""
    if _cache:
        return
    if not PROMPTS_DIR.is_dir():
        log.warning("Prompts directory not found: %s", PROMPTS_DIR)
        return
    for f in PROMPTS_DIR.glob("*.md"):
        try:
            _cache[f.stem] = f.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("Could not read prompt %s: %s", f, e)


def list_prompts() -> list[dict]:
    """Return [{name, length, preview}] for the UI prompt browser."""
    _load()
    out = []
    for name, body in sorted(_cache.items()):
        out.append({
            "name": name,
            "length": len(body),
            "preview": body[:200].replace("\n", " ").strip(),
        })
    return out


def get_prompt(name: str) -> str | None:
    """Return the bundled system prompt by name, or None if missing."""
    _load()
    return _cache.get(name)


def _override_key(name: str) -> str:
    """Settings override field name for a given prompt: e.g. 'narrative' → 'narrativePrompt'."""
    # Convert snake_case → camelCase suffix Prompt
    parts = name.split("_")
    camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
    return f"{camel}Prompt"


def effective_prompt(name: str, settings: dict) -> str:
    """Return the override from settings if non-empty, else the bundled default.
    Raises KeyError if neither exists."""
    override = settings.get(_override_key(name))
    if override and isinstance(override, str) and override.strip():
        return override
    default = get_prompt(name)
    if default is None:
        raise KeyError(f"No bundled prompt named '{name}' and no override in settings")
    return default


def migrate_strip_legacy_prompts() -> int:
    """One-shot startup migration: remove legacy prompt fields from existing
    user settings files. They used to be copied verbatim from defaults at seed
    time and never auto-updated; now they live in app/prompts/*.md and override
    is opt-in via the UI. Idempotent — no-op if already stripped.

    Returns the number of files updated."""
    settings_dir = DATA_DIR / "presets" / "settings"
    if not settings_dir.is_dir():
        return 0
    _load()
    legacy_keys = [_override_key(name) for name in _cache.keys()]
    updated = 0
    for f in settings_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read settings %s: %s", f, e)
            continue
        removed = [k for k in legacy_keys if k in data]
        if not removed:
            continue
        for k in removed:
            del data[k]
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        updated += 1
        log.info("Stripped legacy prompt fields %s from %s", removed, f.name)
    return updated
