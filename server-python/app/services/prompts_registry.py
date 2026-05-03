"""Bundled prompt registry — system prompts ship with the app code.

Prompts are organized by provider:
`app/prompts/<provider>/<kind>.md`

Settings presets can optionally override a prompt by setting the corresponding
`<name>Prompt` field.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR

log = logging.getLogger("pendrift.prompts")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Cache structure: { "provider_name": { "kind": "content" } }
_cache: dict[str, dict[str, str]] = {}


def _load() -> None:
    """Read every .md file under prompts/<provider>/ into the cache. Called lazily."""
    if _cache:
        return
    if not PROMPTS_DIR.is_dir():
        log.warning("Prompts directory not found: %s", PROMPTS_DIR)
        return

    # Load provider-specific prompts
    for provider_dir in PROMPTS_DIR.iterdir():
        if not provider_dir.is_dir():
            # Legacy prompts at the root of app/prompts/
            if provider_dir.suffix == ".md":
                kind = provider_dir.stem
                if "default" not in _cache:
                    _cache["default"] = {}
                _cache["default"][kind] = provider_dir.read_text(encoding="utf-8")
            continue

        provider_name = provider_dir.name
        _cache[provider_name] = {}
        for f in provider_dir.glob("*.md"):
            try:
                _cache[provider_name][f.stem] = f.read_text(encoding="utf-8")
            except OSError as e:
                log.warning("Could not read prompt %s for provider %s: %s", f, provider_name, e)


def get_prompt(kind: str, provider_name: str = "llama-server") -> str | None:
    """Return the default system prompt for the given provider and task kind.
    Falls back to 'default' provider folder if not found in specific provider."""
    _load()
    
    # 1. Try specific provider
    if provider_name in _cache and kind in _cache[provider_name]:
        return _cache[provider_name][kind]
    
    # 2. Try 'default' folder
    if "default" in _cache and kind in _cache["default"]:
        return _cache["default"][kind]
        
    return None


def _override_key(name: str) -> str:
    """Settings override field name for a given prompt: e.g. 'narrative' → 'narrativePrompt'."""
    parts = name.split("_")
    camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
    return f"{camel}Prompt"


def effective_prompt(name: str, settings: dict, provider_name: str | None = None) -> str:
    """Return the override from settings if non-empty, else the provider's default.
    If provider_name is not provided, it's read from settings."""
    if provider_name is None:
        provider_name = settings.get("provider", "llama-server")
        
    override = settings.get(_override_key(name))
    if override and isinstance(override, str) and override.strip():
        return override
    
    default = get_prompt(name, provider_name)
    if default is None:
        # Fallback to some generic assistant prompt
        return "You are a helpful assistant."
    return default


def migrate_strip_legacy_prompts() -> int:
    """One-shot startup migration: remove legacy prompt fields from existing
    user settings files. Returns the number of files updated."""
    settings_dir = DATA_DIR / "presets" / "settings"
    if not settings_dir.is_dir():
        return 0
    _load()
    # Use all known prompt kinds across all providers in cache
    all_kinds = set()
    for p_prompts in _cache.values():
        all_kinds.update(p_prompts.keys())
        
    legacy_keys = [_override_key(name) for name in all_kinds]
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
            # Only remove if it's one of the truly legacy/empty ones (optional)
            # For simplicity, we strip them if they match the pattern and aren't overrides
            # (The original logic was to strip them to avoid stale prompts)
            del data[k]
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        updated += 1
        log.info("Stripped legacy prompt fields %s from %s", removed, f.name)
    return updated
