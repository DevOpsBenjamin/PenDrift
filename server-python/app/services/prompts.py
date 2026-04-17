"""Build message arrays for LLM generation and meta-analysis calls."""
from __future__ import annotations

import json
import re


def _resolve_variables(text: str | None, variables: dict) -> str | None:
    if not text or not variables:
        return text
    return re.sub(r"\{\{(\w+)\}\}", lambda m: variables.get(m.group(1), m.group(0)), text)


def _get_chunk_narrative(chunk: dict) -> str:
    versions = chunk.get("versions")
    if versions:
        if isinstance(versions, str):
            versions = json.loads(versions)
        idx = chunk.get("active_version", chunk.get("activeVersion", 0))
        return versions[idx]["narrative"]
    return chunk.get("narrative", "")


def build_messages(
    *,
    settings: dict,
    characters: list[dict],
    template: dict,
    chunks: list[dict],
    directive: str,
    important_facts: list[str],
    last_meta_after_chunk_index: int | None = None,
    previous_chapter_chunks: list[dict] | None = None,
) -> list[dict]:
    messages = []
    variables = template.get("variables", {})
    resolve = lambda text: _resolve_variables(text, variables)

    # 1. System prompt
    system = settings.get("narrativePrompt", "")

    # Structured output instructions (grammar enforces the format,
    # but the model needs to understand the semantics)
    system += """

## Response Format
You MUST respond as a JSON object with these fields:
- "thinking": Your internal reasoning — plan the scene, consider character states, decide pacing. This is your scratchpad. Be thorough.
- "type": Either "narrative" (you write the scene) or "suggestion" (you propose options for the director to choose from). Default to "narrative". Only use "suggestion" if the directive is very vague or you're at a critical story crossroads where the director should decide.
- "narrative": The actual prose. Write the scene here. If type is "suggestion", leave this empty.
- "suggestions": An array of 2-4 short story direction options. Only fill this if type is "suggestion" OR if you wrote narrative but also want to hint at possible next directions. Otherwise use an empty array."""

    if template.get("scenario"):
        system += f"\n\n## Scenario\n{resolve(template['scenario'])}"

    if template.get("systemPromptAdditions"):
        system += f"\n\n## Style Instructions\n{resolve(template['systemPromptAdditions'])}"

    masked = template.get("maskedIntents", [])
    if masked:
        system += "\n\n## Hidden Narrative Drivers (never reveal these directly)\n"
        system += "\n".join(f"- {resolve(i)}" for i in masked)

    if characters:
        system += "\n\n## Current Character States\n"
        for char in characters:
            name = char.get("name", "Unknown")
            system += f"\n### {name}\n"
            system += f"State: {char.get('current_state', char.get('currentState', ''))}\n"
            traits = char.get("traits", [])
            if isinstance(traits, str):
                traits = json.loads(traits)
            if traits:
                system += f"Traits: {', '.join(traits)}\n"
            events = char.get("key_events", char.get("keyEvents", []))
            if isinstance(events, str):
                events = json.loads(events)
            if events:
                system += f"Key events: {'; '.join(events)}\n"

    if important_facts:
        system += "\n\n## Established Facts\n"
        system += "\n".join(f"- {f}" for f in important_facts)

    messages.append({"role": "system", "content": system})

    # 2. Rolling window of recent chunks
    interval = settings.get("chunkUpdateInterval", 10)
    recent = chunks[-interval:] if chunks else []

    # Cross-chapter context
    if not recent and previous_chapter_chunks:
        cross = previous_chapter_chunks[-2:]
        messages.append({"role": "user", "content": "Context from the end of the previous chapter:"})
        for c in cross:
            messages.append({"role": "assistant", "content": _get_chunk_narrative(c)})

    if recent:
        messages.append({"role": "user", "content": "Begin."})
        window_start = len(chunks) - len(recent)

        for i, chunk in enumerate(recent):
            global_index = window_start + i
            messages.append({"role": "assistant", "content": _get_chunk_narrative(chunk)})

            if last_meta_after_chunk_index is not None and global_index == last_meta_after_chunk_index:
                messages.append({
                    "role": "user",
                    "content": "Character sheets and established facts have been updated based on the narrative so far. The character states above reflect the story up to this point.",
                })

    # 3. Directive
    messages.append({"role": "user", "content": directive})
    return messages


def build_meta_analysis_messages(
    *,
    characters: list[dict],
    recent_chunks: list[dict],
    important_facts: list[str],
    meta_prompt: str,
    previous_meta_results: list[dict] | None = None,
) -> list[dict]:
    messages = []

    messages.append({"role": "system", "content": meta_prompt or "You are a narrative analyst. Return only valid JSON."})

    messages.append({"role": "user", "content": "Here are the current character sheets. Update them based on the narrative that follows."})
    messages.append({"role": "assistant", "content": json.dumps(characters, indent=2)})

    if important_facts:
        messages.append({"role": "user", "content": "Here are the established facts. Keep all of them, only add new ones. Deduplicate if needed."})
        messages.append({"role": "assistant", "content": "\n".join(f"- {f}" for f in important_facts)})

    if previous_meta_results:
        summary = "Previous analyses for reference (build on these):\n"
        for meta in previous_meta_results:
            result = meta.get("result", {})
            if isinstance(result, str):
                result = json.loads(result)
            updates = result.get("characterUpdates", [])
            if updates:
                summary += "\nUpdates: " + "; ".join(f"{c['name']}: {c.get('currentState', '')}" for c in updates)
            facts = result.get("importantFacts", [])
            if facts:
                summary += "\nFacts: " + "; ".join(facts)
        messages.append({"role": "user", "content": summary})

    messages.append({"role": "user", "content": "Here is the recent narrative to analyze:"})
    for chunk in recent_chunks:
        messages.append({"role": "assistant", "content": _get_chunk_narrative(chunk)})

    messages.append({"role": "user", "content": "Analyze the narrative above. Update characters, detect new ones, flag inconsistencies, extract facts. Return ONLY the JSON object."})
    return messages
