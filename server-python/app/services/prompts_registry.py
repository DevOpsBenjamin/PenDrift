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
        
    # 3. Last resort: ask the provider class itself (legacy fallback)
    from app.services.providers import get_provider
    try:
        prov = get_provider(provider_name)
        return prov.get_default_prompt(kind)
    except Exception:
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
