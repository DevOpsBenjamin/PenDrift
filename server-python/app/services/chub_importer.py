"""Import character cards (Chub/TavernAI V2 format) and convert to PenDrift templates via LLM."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

import httpx

from app.services import llm_activity
from app.services.llm import _build_body, _get_lock, generate_completion, llama_sse_completion
from app.services.job_manager import Job
from app.services.prompts_registry import effective_prompt
from app.utils.grammars import TEMPLATE_GRAMMAR

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


async def _llm_template_call(
    messages: list[dict],
    settings: dict,
    *,
    kind: str,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> dict:
    """Shared LLM call for any chub_import-shaped operation (import, rerun,
    enrich). Returns the parsed template body with `thinking` stripped.

    If `job` is provided, llama-server's SSE events (first_token, delta,
    model, usage) are forwarded to the job so the toast bar / Activity view
    can show live token streaming. Without a job, this falls back to the
    buffered `generate_completion` path (legacy callers, no UI streaming).
    """
    if job is None:
        result = await generate_completion(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            grammar=TEMPLATE_GRAMMAR,
            kind=kind,
        )
        raw = result["raw"]
    else:
        body = _build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            grammar=TEMPLATE_GRAMMAR,
        )
        call = llm_activity.register(kind, None)
        llm_activity.attach_task(call, asyncio.current_task())
        full: list[str] = []
        usage: dict = {}
        model_name = ""
        try:
            async with _get_lock():
                llm_activity.mark_running(call)
                job.emit({"type": "llm_start", "kind": kind, "callId": call.id})
                async for ev in llama_sse_completion(body, activity_call=call, kind=kind):
                    if ev["type"] == "delta":
                        full.append(ev["text"])
                    elif ev["type"] == "model":
                        model_name = ev["name"]
                    elif ev["type"] == "usage":
                        usage = ev["data"]
                    job.emit(ev)
            raw = "".join(full)
            stats = {
                "promptTokens": usage.get("prompt_tokens"),
                "completionTokens": usage.get("completion_tokens"),
                "totalTokens": usage.get("total_tokens"),
            }
            llm_activity.mark_done(call, stats=stats, model=model_name, raw_response=raw)
            job.emit({"type": "llm_done", "stats": stats, "modelName": model_name})
        except asyncio.CancelledError:
            llm_activity.mark_done(call, error="cancelled", raw_response="".join(full) or None)
            raise
        except Exception as e:
            llm_activity.mark_done(call, error=str(e), raw_response="".join(full) or None)
            raise

    try:
        template = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("%s: JSON decode failed at char %d/%d: %s", kind, e.pos, len(raw), e.msg)
        raise ValueError(
            f"Model output is not valid JSON ({e.msg} at char {e.pos} of {len(raw)}). "
            f"Check Activity view → recent call → dump file."
        ) from e

    template.pop("thinking", None)
    return template


async def convert_card_to_template(
    card: dict,
    settings: dict,
    *,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
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
    max_tokens: int = 4096,
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
    template["id"] = current_template.get("id") or template.get("id")
    return template


async def rerun_with_current(
    card: dict,
    current_template: dict,
    settings: dict,
    *,
    job: Job | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
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
    # Preserve the existing template id — rerun improves the same template
    template["id"] = current_template.get("id") or template.get("id")
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
