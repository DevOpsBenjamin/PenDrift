"""Import character cards (Chub/TavernAI V2 format) and convert to PenDrift templates via LLM."""
from __future__ import annotations

import json
import logging
import re

import httpx

from app.services.llm import generate_completion

log = logging.getLogger("pendrift.chub_import")

# Fallback prompt if not set in preset — should not normally be used
_DEFAULT_IMPORT_PROMPT = "Convert this character card into a PenDrift template. Return ONLY valid JSON."

# GBNF grammar to force valid PenDrift template JSON output
TEMPLATE_GRAMMAR = r'''
root   ::= "{" ws "\"name\"" ws ":" ws string "," ws "\"description\"" ws ":" ws string "," ws "\"variables\"" ws ":" ws object "," ws "\"characters\"" ws ":" ws characters "," ws "\"scenario\"" ws ":" ws string "," ws "\"maskedIntents\"" ws ":" ws stringarray "," ws "\"systemPromptAdditions\"" ws ":" ws string ws "}"

characters ::= "[" ws character ( "," ws character )* ws "]"
character  ::= "{" ws "\"name\"" ws ":" ws string "," ws "\"description\"" ws ":" ws string "," ws "\"initialState\"" ws ":" ws string ws "}"

stringarray ::= "[" ws string ( "," ws string )* ws "]"

object ::= "{" ws ( objectpair ( "," ws objectpair )* )? ws "}"
objectpair ::= string ws ":" ws string

string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hexchar hexchar hexchar hexchar
hexchar ::= [0-9a-fA-F]

ws ::= [ \t\n\r]*
'''


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


async def convert_card_to_template(
    card: dict,
    settings: dict,
    *,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    use_grammar: bool = True,
) -> dict:
    """Use the LLM to convert a character card into a PenDrift template.

    The conversion prompt is read from settings['chubImportPrompt'].
    """
    import_prompt = settings.get("chubImportPrompt") or _DEFAULT_IMPORT_PROMPT

    messages = [
        {"role": "system", "content": import_prompt},
        {"role": "user", "content": _build_conversion_input(card)},
    ]

    result = await generate_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        grammar=TEMPLATE_GRAMMAR if use_grammar else None,
    )

    text = result["narrative"]

    # Parse the JSON output
    try:
        template = json.loads(text)
    except json.JSONDecodeError:
        # Try extracting from markdown block
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            template = json.loads(m.group(1))
        else:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                template = json.loads(m.group(0))
            else:
                raise ValueError(f"LLM returned unparseable output: {text[:200]}")

    # Generate a stable ID from the name
    template_id = re.sub(r"[^a-z0-9]+", "_", template.get("name", "imported").lower()).strip("_")
    template["id"] = template_id

    return template
