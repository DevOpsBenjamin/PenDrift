"""Import character cards (Chub/TavernAI V2 format) and convert to PenDrift templates via LLM."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx

from app.services.llm import run_llm_buffered
from app.services.job_manager import Job
from app.services.prompts_registry import effective_prompt

log = logging.getLogger("pendrift.chub_import")


async def fetch_chub_card(url_or_path: str) -> dict:
    """Fetch a character card from chub.ai or parse a local JSON/PNG."""
    # If it's a chub.ai URL, extract the path
    # URLs look like: https://chub.ai/characters/username/character-name
    match = re.match(r"https?://chub\.ai/characters/(.+?)(?:\?.*)?$", url_or_path)
    if match:
        full_path = match.group(1)
        async with httpx.AsyncClient(timeout=30) as client:
            # Try to get the JSON directly from the API first
            try:
                r = await client.get(
                    f"https://api.chub.ai/api/characters/{full_path}",
                    headers={"User-Agent": "PenDrift/0.2"},
                    follow_redirects=True,
                )
                if r.status_code == 200:
                    data = r.json()
                    if "node" in data:
                        return _normalize_card(data["node"])
                    return _normalize_card(data)
            except Exception:
                pass

            # Fallback: try the search API
            try:
                r = await client.get(
                    "https://api.chub.ai/search",
                    params={"search": full_path.split("/")[-1], "first": 1},
                    headers={"User-Agent": "PenDrift/0.2"},
                )
                if r.status_code == 200:
                    results = r.json()
                    nodes = results.get("data", results.get("nodes", []))
                    if nodes:
                        return _normalize_card(nodes[0])
            except Exception:
                pass

        raise ValueError(f"Could not fetch card from chub.ai: {url_or_path}")

    # If it's raw JSON
    if isinstance(url_or_path, str) and url_or_path.strip().startswith("{"):
        return _normalize_card(json.loads(url_or_path))

    raise ValueError("Provide a chub.ai URL or a JSON character card")


def _normalize_card(data: dict) -> dict:
    """Normalize various card formats to a flat structure."""
    # V2 format: data nested under "data" key
    if data.get("spec") == "chara_card_v2" and "data" in data:
        return data["data"]
    if "data" in data and isinstance(data["data"], dict) and "name" in data["data"]:
        return data["data"]
    # Already flat
    if "name" in data:
        return data
    # Chub API wraps in various ways
    for key in ("definition", "character", "card"):
        if key in data and isinstance(data[key], dict):
            return _normalize_card(data[key])
    return data


def _build_conversion_input(card: dict) -> str:
    """Build the user message showing the card data to the LLM."""
    parts = []

    parts.append(f"# Character Card: {card.get('name', 'Unknown')}\n")

    if card.get("description"):
        parts.append(f"## Description\n{card['description']}\n")

    if card.get("personality"):
        parts.append(f"## Personality\n{card['personality']}\n")

    if card.get("scenario"):
        parts.append(f"## Scenario\n{card['scenario']}\n")

    if card.get("first_mes"):
        parts.append(f"## First Message (style reference + character dynamics — do NOT include in output, but extract subtext)\n{card['first_mes']}\n")

    if card.get("alternate_greetings"):
        greetings = card["alternate_greetings"]
        if isinstance(greetings, list) and greetings:
            parts.append("## Alternate Greetings (these reveal character dynamics and hidden motivations — extract subtext, do NOT include in output)\n")
            for i, g in enumerate(greetings, 1):
                parts.append(f"### Greeting {i}\n{g}\n")

    if card.get("mes_example"):
        parts.append(f"## Example Messages (style reference only — do NOT include in output)\n{card['mes_example']}\n")

    if card.get("system_prompt"):
        # Strip {{original}} placeholder
        sys_prompt = card["system_prompt"].replace("{{original}}", "").strip()
        if sys_prompt:
            parts.append(f"## System Prompt (reinterpret for PenDrift, do NOT copy)\n{sys_prompt}\n")

    if card.get("post_history_instructions"):
        parts.append(f"## Post-History Instructions (reinterpret if useful)\n{card['post_history_instructions']}\n")

    if card.get("creator_notes"):
        # Strip HTML/CSS — only keep text content if any
        notes = card["creator_notes"]
        # Remove <style>...</style> blocks
        notes = re.sub(r"<style[\s\S]*?</style>", "", notes, flags=re.IGNORECASE)
        # Remove HTML tags
        notes = re.sub(r"<[^>]+>", " ", notes)
        # Collapse whitespace
        notes = re.sub(r"\s+", " ", notes).strip()
        if notes and len(notes) > 20:
            parts.append(f"## Creator Notes (context only, may contain useful scenario info)\n{notes}\n")

    if card.get("tags"):
        tags = card["tags"] if isinstance(card["tags"], list) else []
        if tags:
            parts.append(f"## Tags\n{', '.join(tags)}\n")

    parts.append("\nConvert this character card into a PenDrift template. Return ONLY the JSON.")
    return "\n".join(parts)


def _resolve_template_max_tokens(settings: dict, explicit: int | None) -> int:
    """Pick max_tokens for a template-shaped flow (chub_import / enrich /
    rerun). Caller's explicit value wins; otherwise the preset's `maxTokens`;
    otherwise 4096 as the conservative local-model default.

    Templates routinely need 6-10k output tokens once thinking + full body
    are accounted for, so external providers like Grok should be configured
    with a generous `maxTokens` (16k+) in their preset."""
    if explicit is not None:
        return explicit
    val = settings.get("maxTokens")
    if isinstance(val, int) and val > 0:
        return val
    return 4096


async def _llm_template_call(
    messages: list[dict],
    settings: dict,
    *,
    kind: str,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict:
    """Shared LLM call for any chub_import-shaped operation (import, rerun,
    enrich). Returns the parsed template body — `thinking` is preserved on
    the body so it gets persisted with the template version, letting the
    user inspect what the model understood at conversion time.

    Forwards LLM events to `job` (when provided) so the toast bar / Activity
    view see live token streaming."""
    resolved_max_tokens = _resolve_template_max_tokens(settings, max_tokens)
    result = await run_llm_buffered(
        messages,
        settings=settings,
        kind=kind,
        job=job,
        temperature=temperature,
        max_tokens=resolved_max_tokens,
    )
    raw = result["raw"]
    try:
        template = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("%s: JSON decode failed at char %d/%d: %s", kind, e.pos, len(raw), e.msg)
        raise ValueError(
            f"Model output is not valid JSON ({e.msg} at char {e.pos} of {len(raw)}). "
            f"Check Activity view → recent call → dump file."
        ) from e
    return template


async def convert_card_to_template(
    card: dict,
    settings: dict,
    *,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict:
    """Convert a character card into a PenDrift template (fresh import).

    The conversion prompt is the bundled `chub_import` prompt unless the
    preset overrides it via `chubImportPrompt`. Pass a `job` to stream live
    LLM events (token deltas, first_token, usage) into the toast bar.
    """
    messages = [
        {"role": "system", "content": effective_prompt("chub_import", settings)},
        {"role": "user", "content": _build_conversion_input(card)},
    ]
    template = await _llm_template_call(
        messages, settings, kind="chub-import", job=job,
        temperature=temperature, max_tokens=max_tokens,
    )
    template_id = re.sub(r"[^a-z0-9]+", "_", template.get("name", "imported").lower()).strip("_")
    template["id"] = template_id
    return template


async def enrich_with_new_card(
    new_card: dict,
    current_template: dict,
    settings: dict,
    *,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict:
    """Merge a NEW card (different character from the same shared universe)
    into the existing template. Used to grow a multi-character template from
    multiple chub cards (e.g. add Ethan and Lauren to a Tiffany template).

    The system prompt is the bundled `enrich` prompt; the user message
    contains the new card and the current template body. Pass a `job` to
    stream live LLM events into the toast bar."""
    current_for_prompt = {k: v for k, v in current_template.items() if k != "coverImage"}
    user_msg = (
        f"# New Card (to merge into the template)\n\n{_build_conversion_input(new_card)}\n\n"
        f"---\n\n"
        f"# Current Template (preserve what's good, enrich with new info)\n\n"
        f"```json\n{json.dumps(current_for_prompt, indent=2, ensure_ascii=False)}\n```\n\n"
        f"Merge the new card into the current template now. Output the complete enriched template."
    )
    messages = [
        {"role": "system", "content": effective_prompt("enrich", settings)},
        {"role": "user", "content": user_msg},
    ]
    template = await _llm_template_call(
        messages, settings, kind="enrich", job=job,
        temperature=temperature, max_tokens=max_tokens,
    )
    # Pin id and name to the existing template — enrich never renames or
    # re-ids the template it's merging into (the model sometimes regenerates
    # the title from the new card alone, which is wrong for a merge).
    template["id"] = current_template.get("id") or template.get("id")
    if current_template.get("name"):
        template["name"] = current_template["name"]
    return template


async def rerun_with_current(
    card: dict,
    current_template: dict,
    settings: dict,
    *,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict:
    """Re-analyze a card against the CURRENT template to fix/fill/correct.

    The system prompt is the bundled `rerun` prompt; the user message
    includes both the original source card and the current template body
    so the model can audit and improve. Pass a `job` to stream live LLM
    events into the toast bar."""
    current_for_prompt = {k: v for k, v in current_template.items() if k != "coverImage"}
    user_msg = (
        f"# Original Card\n\n{_build_conversion_input(card)}\n\n"
        f"---\n\n"
        f"# Current Template (for audit & improvement)\n\n"
        f"```json\n{json.dumps(current_for_prompt, indent=2, ensure_ascii=False)}\n```\n\n"
        f"Audit the current template against the original card. Produce the improved template now."
    )
    messages = [
        {"role": "system", "content": effective_prompt("rerun", settings)},
        {"role": "user", "content": user_msg},
    ]
    template = await _llm_template_call(
        messages, settings, kind="rerun", job=job,
        temperature=temperature, max_tokens=max_tokens,
    )
    # Pin id and name to the existing template — rerun is an audit/improve
    # pass on the SAME template, so the title shouldn't drift even if the
    # model decides the focus has shifted.
    template["id"] = current_template.get("id") or template.get("id")
    if current_template.get("name"):
        template["name"] = current_template["name"]
    return template


async def download_card_avatar(card: dict) -> tuple[bytes, str] | None:
    """Best-effort fetch of the card's avatar URL. Returns (content_bytes,
    extension_with_dot) or None if no avatar / fetch failed."""
    url = card.get("avatar")
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return None
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "PenDrift/0.2"})
            if r.status_code != 200:
                return None
            ct = r.headers.get("content-type", "").lower()
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"
            elif "gif" in ct:
                ext = ".gif"
            else:
                ext = ".png"
            return r.content, ext
    except (httpx.HTTPError, OSError) as e:
        log.warning("Could not fetch avatar from %s: %s", url, e)
        return None
