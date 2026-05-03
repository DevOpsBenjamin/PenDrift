"""Build message arrays for LLM generation and meta-analysis calls."""
from __future__ import annotations

import json
import re

from app.services.prompts_registry import effective_prompt


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
    previous_attempt: dict | None = None,
) -> list[dict]:
    messages = []
    variables = template.get("variables", {})
    resolve = lambda text: _resolve_variables(text, variables)

    # 1. System prompt
    provider_name = settings.get("provider", "llama-server")
    system = effective_prompt("narrative", settings, provider_name)

    # Structured output instructions (grammar enforces the format,
    # but the model needs to understand the semantics)
    system += """

## Response Format
You MUST respond as a JSON object with these fields:
- "thinking": Your internal reasoning — plan the scene, consider character states, decide pacing. This is your scratchpad. Be thorough.
- "narrative": The actual prose. Write the scene here.
- "suggestions": An array of 2-4 NEW DIRECTION suggestions for what could happen next, presented to the director as clickable hints. Each entry MUST be a COMPLETE, ACTIONABLE sentence (15-150 chars) describing a specific next move.

# IMPORTANT: the director's preferred mode

The director may want to WATCH the story unfold rather than constantly write directives. After your narrative chunk:
- ALWAYS include 2-4 suggestions when you end at a natural pause.
- Suggestions should branch in DIFFERENT directions — give the director a real choice (different tones, different character actions, different stakes).
- Never end a chunk by asking the director a question, never break the fourth wall, never write "what does X do?".

Rules for `suggestions`:
- Output EXACTLY the number of meaningful options you have. 
- NEVER pad with filler, separators, placeholder strings like "," or " " — every entry is a real suggestion or it's omitted.
- Skip generic ("they continue talking") — be SPECIFIC to THIS scene's state and characters.
- If you genuinely cannot think of suggestions, output []."""

    if template.get("scenario"):
        system += f"\n\n## Scenario\n{resolve(template['scenario'])}"

    milestones = template.get("milestones", [])
    if milestones:
        system += "\n\n## Story Milestones (narrative waypoints — the timeline can move toward and through these)\n"
        system += "These are key moments the story may progress through. The director can request a jump to any of them at any time. When narrating, you may foreshadow upcoming milestones or reference past ones. They give the story a known shape without forcing a fixed pace.\n\n"
        system += "\n".join(f"- {resolve(m)}" for m in milestones)

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

    # 3. (regen only) Discarded previous attempt for context
    if previous_attempt:
        prev_narr = previous_attempt.get("narrative", "")
        prev_directive = previous_attempt.get("directive") or ""
        prev_thinking = previous_attempt.get("thinking") or ""
        warning = (
            "⚠️ DISCARDED PREVIOUS ATTEMPT — context only.\n\n"
            "Below is your previous attempt at this same scene. The director was NOT satisfied "
            "and is asking for a fresh take. This attempt IS DISCARDED — it does not exist in "
            "the story. The narrative above (the recent chunks) is still the latest validated state.\n\n"
            "Treat the previous attempt as a NEGATIVE EXAMPLE of one direction you took. You have "
            "full creative freedom to take a completely different angle: change tone, pacing, what "
            "characters say or do, even what happens. The director's NEW instructions (below) are "
            "what matters — produce a fresh attempt that addresses them, ignoring whether you might "
            "echo or contradict the previous attempt."
        )
        if prev_directive:
            warning += f"\n\nPrevious directive (now superseded): {prev_directive}"
        messages.append({"role": "user", "content": warning})
        if prev_thinking:
            messages.append({
                "role": "user",
                "content": f"Previous attempt's reasoning (for transparency only):\n{prev_thinking}",
            })
        if prev_narr:
            messages.append({
                "role": "user",
                "content": "Previous attempt's narrative (DISCARDED, do not continue from this):",
            })
            messages.append({"role": "assistant", "content": prev_narr})
        messages.append({
            "role": "user",
            "content": "The director's NEW instructions follow. Produce a fresh attempt that ignores the discarded version.",
        })

    # 4. Directive
    messages.append({"role": "user", "content": directive})
    return messages


def build_query_messages(
    *,
    question: str,
    template: dict,
    characters: list[dict],
    important_facts: list[str],
    recent_chunks: list[dict],
    settings: dict,
    history: list[dict] | None = None,
) -> list[dict]:
    """Build the message array for an Ask-the-Narrator query."""
    variables = template.get("variables", {})
    resolve = lambda text: _resolve_variables(text, variables)

    provider_name = settings.get("provider", "llama-server")
    query_system = effective_prompt("query", settings, provider_name)
    messages = [{"role": "system", "content": query_system}]

    # Context dump (template + masked intents + chars + facts)
    ctx_parts = []
    if template.get("scenario"):
        ctx_parts.append(f"## Scenario\n{resolve(template['scenario'])}")
    milestones = template.get("milestones", [])
    if milestones:
        ctx_parts.append("## Story Milestones (narrative waypoints the story can progress through)\n"
                         + "\n".join(f"- {resolve(m)}" for m in milestones))
    if template.get("systemPromptAdditions"):
        ctx_parts.append(f"## Style\n{resolve(template['systemPromptAdditions'])}")
    masked = template.get("maskedIntents", [])
    if masked:
        ctx_parts.append("## Hidden Narrative Drivers (masked intents — the director knows these)\n"
                         + "\n".join(f"- {resolve(i)}" for i in masked))
    if characters:
        char_lines = ["## Characters"]
        for char in characters:
            name = char.get("name", "Unknown")
            char_lines.append(f"\n### {name}")
            char_lines.append(f"State: {char.get('current_state', char.get('currentState', ''))}")
            traits = char.get("traits", [])
            if isinstance(traits, str):
                traits = json.loads(traits)
            if traits:
                char_lines.append(f"Traits: {', '.join(traits)}")
            events = char.get("key_events", char.get("keyEvents", []))
            if isinstance(events, str):
                events = json.loads(events)
            if events:
                char_lines.append(f"Key events: {'; '.join(events)}")
        ctx_parts.append("\n".join(char_lines))
    if important_facts:
        ctx_parts.append("## Established Facts\n" + "\n".join(f"- {f}" for f in important_facts))
    if ctx_parts:
        messages.append({"role": "user", "content": "Here is the story context:\n\n" + "\n\n".join(ctx_parts)})
        messages.append({"role": "assistant", "content": "Got it — I have the full context including masked intents."})

    # Recent narrative for tone/state
    if recent_chunks:
        messages.append({"role": "user", "content": "Recent narrative chunks (most recent last):"})
        for chunk in recent_chunks:
            messages.append({"role": "assistant", "content": _get_chunk_narrative(chunk)})

    # Past Q&A in this session for continuity
    if history:
        for qa in history:
            q = qa.get("question", "")
            a = qa.get("answer", "")
            if q:
                messages.append({"role": "user", "content": q})
            if a:
                messages.append({"role": "assistant", "content": json.dumps({"thinking": "", "answer": a}, ensure_ascii=False)})

    messages.append({"role": "user", "content": question})
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

    messages.append({"role": "user", "content": "Here are the current character sheets. Update ONLY characters who appeared in the recent narrative — others stay as-is. Your output for each character REPLACES the existing sheet."})
    messages.append({"role": "assistant", "content": json.dumps(characters, indent=2)})

    if important_facts:
        messages.append({"role": "user", "content": "Here is the current facts list. Your `importantFacts` output REPLACES this list entirely — decide what to KEEP (still relevant), DROP (obsolete or noise), MERGE (redundant variants), and ADD (truly new). Anything you omit is gone from memory."})
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

    messages.append({"role": "user", "content": "Analyze the narrative above. Update only characters who appeared, detect genuinely new ones, flag concrete contradictions, and emit the new facts list (REPLACES the current). Be selective — empty arrays are fine."})
    return messages
