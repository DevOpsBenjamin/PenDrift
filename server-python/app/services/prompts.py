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


def _coerce_list(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            return json.loads(value) or []
        except (json.JSONDecodeError, TypeError):
            return []
    return value or []


def _format_character_block(characters: list[dict]) -> str:
    """Render per-character sheets with the full structured layout: identity,
    voice, appearance, backstory (+ additions), state, traits, key events,
    hidden drivers. Empty fields are skipped — the model never sees blank
    sections.

    Reads either snake_case or camelCase keys (DB rows arrive snake_case;
    in-flight character dicts arrive camelCase).
    """
    def _get(char, *keys):
        for k in keys:
            if k in char and char[k] not in (None, ""):
                return char[k]
        return ""

    lines = []
    for char in characters:
        name = char.get("name", "Unknown")
        lines.append(f"### {name}")

        identity = _get(char, "identity")
        voice = _get(char, "voice")
        appearance = _get(char, "appearance")
        backstory = _get(char, "backstory")
        backstory_additions = _coerce_list(char.get("backstory_additions") or char.get("backstoryAdditions"))
        current_state = _get(char, "current_state", "currentState")
        traits = _coerce_list(char.get("traits"))
        events = _coerce_list(char.get("key_events") or char.get("keyEvents"))
        masked_intents = _coerce_list(char.get("masked_intents") or char.get("maskedIntents"))

        if identity:
            lines.append(f"Identity: {identity}")
        if voice:
            lines.append(f"Voice: {voice}")
        if appearance:
            lines.append(f"Appearance: {appearance}")
        if backstory or backstory_additions:
            lines.append("Backstory:")
            if backstory:
                lines.append(f"  {backstory}")
            for add in backstory_additions:
                lines.append(f"  + {add}")
        if current_state:
            lines.append(f"State: {current_state}")
        if traits:
            lines.append(f"Traits: {', '.join(traits)}")
        if events:
            lines.append(f"Key events: {'; '.join(events)}")
        if masked_intents:
            lines.append("Hidden drivers (subtext only — never name in prose):")
            for intent in masked_intents:
                lines.append(f"  - {intent}")
        lines.append("")  # blank line between characters
    return "\n".join(lines).rstrip()


def _has_per_character_intents(characters: list[dict]) -> bool:
    return any(_coerce_list(c.get("masked_intents") or c.get("maskedIntents")) for c in characters)


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
    pending_milestones: list[str] | None = None,
) -> list[dict]:
    """Build the message array for narrative generation.

    Layout:
      [system]    Stable craft instructions only (provider's narrative.md prompt).
                  Cache-friendly — same content across every chunk of every session
                  using the same provider, so xAI's prompt cache stays hot.

      [user/asst] Setup pseudo-turn: active arc (next pending milestone) + style.
                  Scenario is consumed by initial meta into character.currentState,
                  so it never appears here. Full milestone list is replaced by the
                  next pending milestone only — the model sees forward direction,
                  not the whole roadmap.

      [user/asst] (Legacy fallback only) Global hidden drivers from
                  template.maskedIntents — used when the session was created
                  before per-character masked_intents existed. New sessions carry
                  hidden drivers per-character inside the character block.

      [user/asst] Character sheets (full structured layout: identity / voice /
                  appearance / backstory + additions / state / traits / events /
                  hidden drivers) + established facts.

      [user]      "Begin."  (or cross-chapter context if the chapter is empty)
      [asst]      chunk 1 narrative
       ...
      [regen only] Discarded previous attempt block — narrative only.
      [user]      Directive.
    """
    messages = []
    variables = template.get("variables", {})
    resolve = lambda text: _resolve_variables(text, variables)

    # 1. System: stable craft instructions only.
    provider_name = settings.get("provider", "llama-server")
    messages.append({
        "role": "system",
        "content": effective_prompt("narrative", settings, provider_name),
    })

    # 2. Setup pseudo-turn: active arc + style.
    setup_parts = []

    # Active arc = next pending milestone. Falls back to template.milestones[0]
    # for legacy sessions whose pending_milestones array wasn't populated by
    # the initial meta call.
    active_arc = None
    if pending_milestones:
        active_arc = pending_milestones[0]
    elif template.get("milestones"):
        active_arc = template["milestones"][0]
    if active_arc:
        setup_parts.append(
            f"## Active Arc\n{resolve(active_arc)}\n\n"
            "Soft direction the story is currently moving toward — not a goal to ram into. "
            "Let it shape pacing and character drivers; let the director's chunks decide whether and how it lands."
        )

    if template.get("systemPromptAdditions"):
        setup_parts.append(f"## Style Instructions\n{resolve(template['systemPromptAdditions'])}")

    if setup_parts:
        messages.append({
            "role": "user",
            "content": "Story setup for this session:\n\n" + "\n\n".join(setup_parts),
        })
        messages.append({"role": "assistant", "content": "Got it."})

    # 3. Hidden drivers pseudo-turn — LEGACY FALLBACK ONLY.
    # New sessions carry masked intents per-character (set at session creation
    # by the initial meta call). When any character has populated masked_intents,
    # the per-character block is the source of truth and we skip this top-level
    # turn. When no character carries them but the template has template.maskedIntents
    # (an old session), fall back to the legacy global block.
    if not _has_per_character_intents(characters):
        masked = template.get("maskedIntents", [])
        if masked:
            masked_text = "\n".join(f"- {resolve(i)}" for i in masked)
            messages.append({
                "role": "user",
                "content": "Hidden narrative drivers — never reveal these directly in prose, let them shape behavior through subtext:\n\n" + masked_text,
            })
            messages.append({
                "role": "assistant",
                "content": "Internalized. I'll let those drive character behavior without naming them.",
            })

    # 4. Dynamic state pseudo-turn — characters + facts as assistant content,
    #    since they came from prior meta-analysis output.
    state_parts = []
    if characters:
        state_parts.append("## Character Sheets\n" + _format_character_block(characters))
    if important_facts:
        state_parts.append("## Established Facts\n" + "\n".join(f"- {f}" for f in important_facts))

    if state_parts:
        messages.append({
            "role": "user",
            "content": "Here are the latest character sheets and established facts (from analysis of the narrative so far). Hidden drivers under each character shape behavior through subtext — never name them in narration.",
        })
        messages.append({"role": "assistant", "content": "\n\n".join(state_parts)})

    # 5. Rolling window of recent chunks.
    interval = settings.get("chunkUpdateInterval", 10)
    recent = chunks[-interval:] if chunks else []

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
                    "content": "Character sheets and established facts have been updated based on the narrative so far. The states above reflect the story up to this point.",
                })

    # 6. (regen only) Discarded previous attempt — narrative only, no thinking dump.
    if previous_attempt:
        prev_narr = previous_attempt.get("narrative", "")
        prev_directive = previous_attempt.get("directive") or ""
        warning = (
            "⚠️ DISCARDED PREVIOUS ATTEMPT — context only.\n\n"
            "The director was not satisfied with the prior attempt at this chunk. "
            "It is DISCARDED — it does not exist in the story. The narrative above is still the latest validated state.\n\n"
            "Treat it as a NEGATIVE EXAMPLE. Take a different angle. Avoid reproducing its phrasing, "
            "structure, or emotional arc. The director's NEW instructions below are what matters — "
            "ignore whether you might echo or contradict the previous attempt."
        )
        if prev_directive:
            warning += f"\n\nPrevious directive (now superseded): {prev_directive}"
        messages.append({"role": "user", "content": warning})
        if prev_narr:
            messages.append({
                "role": "user",
                "content": "Previous attempt's narrative (DISCARDED — do not echo, paraphrase, or build on it):",
            })
            messages.append({"role": "assistant", "content": prev_narr})
        messages.append({
            "role": "user",
            "content": "The director's NEW instructions follow. Produce a fresh attempt that ignores the discarded version.",
        })

    # 7. Directive.
    messages.append({"role": "user", "content": directive})
    return messages


def build_epilogue_messages(
    *,
    settings: dict,
    template: dict,
    characters: list[dict],
    important_facts: list[str],
    last_chunks: list[dict],
    chapter_titles: list[str],
) -> list[dict]:
    """Build the message array for epilogue generation. Mirrors `build_messages`
    but uses the `epilogue` system prompt and adds the chapter-arc summary so
    the model can land the closure with the full shape of the story in mind.

    `last_chunks` is the tail end of the LAST FINALIZED chapter — those are the
    chunks the epilogue must tonally land off of. We don't pass the full session
    history (the meta-derived character states + facts already summarize it).
    """
    variables = template.get("variables", {})
    resolve = lambda text: _resolve_variables(text, variables)

    provider_name = settings.get("provider", "llama-server")
    messages = [{
        "role": "system",
        "content": effective_prompt("epilogue", settings, provider_name),
    }]

    setup_parts = []
    if template.get("scenario"):
        setup_parts.append(f"## Scenario (the original promise)\n{resolve(template['scenario'])}")
    milestones = template.get("milestones", [])
    if milestones:
        setup_parts.append(
            "## Story Milestones (waypoints the story moved through)\n"
            + "\n".join(f"- {resolve(m)}" for m in milestones)
        )
    if template.get("systemPromptAdditions"):
        setup_parts.append(f"## Style Instructions\n{resolve(template['systemPromptAdditions'])}")
    if setup_parts:
        messages.append({"role": "user", "content": "Story setup:\n\n" + "\n\n".join(setup_parts)})
        messages.append({"role": "assistant", "content": "Got it."})

    masked = template.get("maskedIntents", [])
    if masked:
        masked_text = "\n".join(f"- {resolve(i)}" for i in masked)
        messages.append({
            "role": "user",
            "content": "Hidden narrative drivers — most of these become observable truths now in the epilogue, but never label them; let them land as behavior or final-state imagery:\n\n" + masked_text,
        })
        messages.append({"role": "assistant", "content": "Internalized."})

    state_parts = []
    if characters:
        state_parts.append("## Final Character States\n" + _format_character_block(characters))
    if important_facts:
        state_parts.append("## Established Facts\n" + "\n".join(f"- {f}" for f in important_facts))
    if state_parts:
        messages.append({"role": "user", "content": "Latest character snapshots and established facts (as of the final chapter):"})
        messages.append({"role": "assistant", "content": "\n\n".join(state_parts)})

    if chapter_titles:
        arc = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(chapter_titles))
        messages.append({"role": "user", "content": "Shape of the arc you are closing (chapter titles, in order):\n\n" + arc})
        messages.append({"role": "assistant", "content": "Noted."})

    if last_chunks:
        messages.append({"role": "user", "content": "Final chunks of the last chapter — the EXACT tone and rhythm to land off of:"})
        for c in last_chunks:
            messages.append({"role": "assistant", "content": _get_chunk_narrative(c)})

    messages.append({
        "role": "user",
        "content": (
            "Write the epilogue now. Use a deliberate time jump announced in the opening line. "
            "Resolve each main character's arc with appropriate weight. Match the tone of the "
            "chunks above and the template — do not default to a happy ending if the story "
            "didn't earn it. Land on a single final image. 10-14 paragraphs."
        ),
    })
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
        ctx_parts.append("## Characters\n\n" + _format_character_block(characters))
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


def build_template_query_messages(
    *,
    question: str,
    template: dict,
    settings: dict,
    history: list[dict] | None = None,
    session_context: dict | None = None,
) -> list[dict]:
    """Build the message array for an Ask-the-Template meta-analytical Q&A.

    Layout:
      [system]    template_query prompt
      [user]      "Here is the template you are being asked about:"
      [asst]      <full template JSON>
      [user]      "Got it." (mirroring the standard pseudo-turn pattern so the
                  template is treated as already-internalized, not pending
                  instructions)

      [optional session evidence]:
        [user]    "This template has been used in a real session. Here is the
                  evidence: the session's recent narrative chunks and the
                  in-story Q&A the user asked. Use this as ground truth for
                  what the template actually produces."
        [asst]    serialized evidence

      [optional history]:
        for each past Q&A about THIS template:
          [user]    question
          [asst]    JSON answer

      [user]      Current question.

    `session_context` (optional): {
        "session_id": str,
        "session_title": str,
        "recent_chunks": [chunk dicts as in build_messages],
        "session_asks": [{"question": str, "answer": str}, ...],
    }
    """
    provider_name = settings.get("provider", "llama-server")
    template_system = effective_prompt("template_query", settings, provider_name)
    messages: list[dict] = [{"role": "system", "content": template_system}]

    messages.append({
        "role": "user",
        "content": "Here is the template you are being asked about. Treat it as the source of truth — every field matters:",
    })
    messages.append({
        "role": "assistant",
        "content": json.dumps(template, indent=2, ensure_ascii=False),
    })
    messages.append({
        "role": "user",
        "content": "Got it. Now I'll ask questions about this template's structure, goals, gaps, and encoded references.",
    })
    messages.append({
        "role": "assistant",
        "content": "Understood. I have the template internalized and will analyze it as a meta-analyst, decoding any implicit markers and flagging structural issues.",
    })

    if session_context:
        evidence_parts = [
            f"This template has been used in a session titled \"{session_context.get('session_title', 'Untitled')}\". "
            "Here is real evidence of what the template actually produced when run by the model. "
            "Use this as ground truth: the gap between the template's stated intent and what it actually generated tells you where the template is under-specified."
        ]

        recent_chunks = session_context.get("recent_chunks") or []
        if recent_chunks:
            chunk_texts = []
            for i, c in enumerate(recent_chunks):
                chunk_texts.append(f"### Recent chunk {i + 1}\n{_get_chunk_narrative(c)}")
            evidence_parts.append("## Recent narrative chunks (most recent last)\n\n" + "\n\n".join(chunk_texts))

        session_asks = session_context.get("session_asks") or []
        if session_asks:
            ask_lines = []
            for qa in session_asks:
                q = qa.get("question", "").strip()
                a = qa.get("answer", "").strip()
                if not q or not a:
                    continue
                ask_lines.append(f"### Q: {q}\n\nA: {a}")
            if ask_lines:
                evidence_parts.append(
                    "## In-story Q&A from this session (the user already asked the in-story narrator these)\n\n"
                    + "\n\n".join(ask_lines)
                )

        messages.append({"role": "user", "content": "\n\n".join(evidence_parts)})
        messages.append({
            "role": "assistant",
            "content": "Internalized. I'll cross-reference what the template ASKS for against what it ACTUALLY produced when interrogating the structural gaps.",
        })

    if history:
        for qa in history:
            q = (qa.get("question") or "").strip()
            a = (qa.get("answer") or "").strip()
            if not q:
                continue
            messages.append({"role": "user", "content": q})
            if a:
                messages.append({
                    "role": "assistant",
                    "content": json.dumps({"answer": a}, ensure_ascii=False),
                })

    messages.append({"role": "user", "content": question})
    return messages


def build_template_rewrite_messages(
    *,
    template: dict,
    feedback: str,
    selected_asks: list[dict] | None = None,
    settings: dict,
) -> list[dict]:
    """Build the message array for a Template Rewrite call.

    Layout:
      [system]   template_rewrite prompt (schema + craft rules)
      [user]     "Here is the template you must rewrite. Echo `id` and
                  `coverImage` verbatim, change everything else as the
                  feedback asks."
      [asst]     <full template JSON>
      [user]     "Got it. Now apply the feedback below."
      [if asks]  "These meta-analytical Q&A about this template are the
                  diagnostic ground truth — let them guide which fields to
                  rewrite and how. Each Q&A is a Q the user asked and an A
                  from a previous meta-analyst pass:"
      [asst]     formatted Q&A list
      [user]     "User's feedback (what to change in the rewrite):"
      [user]     <feedback text>
      [user]     "Output the new template now — full JSON, same schema,
                  every field present. No commentary."
    """
    provider_name = settings.get("provider", "llama-server")
    rewrite_system = effective_prompt("template_rewrite", settings, provider_name)

    messages: list[dict] = [{"role": "system", "content": rewrite_system}]

    messages.append({
        "role": "user",
        "content": "Here is the current template you must rewrite. Echo `id` and `coverImage` verbatim; change other fields as the feedback below requires. Same schema, every field present.",
    })
    messages.append({
        "role": "assistant",
        "content": json.dumps(template, indent=2, ensure_ascii=False),
    })
    messages.append({
        "role": "user",
        "content": "Got it — I have the current template internalized. Apply the feedback now and any selected diagnostic Q&A.",
    })
    messages.append({
        "role": "assistant",
        "content": "Ready. Awaiting feedback and diagnostic Q&A.",
    })

    if selected_asks:
        ask_blocks = []
        for qa in selected_asks:
            q = (qa.get("question") or "").strip()
            a = (qa.get("answer") or "").strip()
            if not q or not a:
                continue
            ask_blocks.append(f"### Q: {q}\n\nA: {a}")
        if ask_blocks:
            messages.append({
                "role": "user",
                "content": (
                    "Diagnostic Q&A about this template (selected by the user as relevant). "
                    "Each Q&A surfaced a structural gap, a coded reference, a missing milestone, "
                    "or a contradiction. Use these as ground truth alongside the feedback:"
                ),
            })
            messages.append({
                "role": "assistant",
                "content": "\n\n".join(ask_blocks),
            })

    messages.append({
        "role": "user",
        "content": (
            "User's feedback for this rewrite (what they want changed):\n\n"
            f"{feedback.strip()}\n\n"
            "Output the new template now — full JSON, same schema as input, every field present, "
            "`id` and `coverImage` echoed verbatim. No commentary, no preamble, just the JSON object."
        ),
    })
    return messages


def build_initial_meta_messages(
    *,
    template: dict,
    variables: dict,
    settings: dict,
) -> list[dict]:
    """Build messages for the initial meta call that runs once at session
    creation. The model receives the full template + variables and produces
    structured per-character session state plus session-level lists.

    Layout:
      [system]    meta_initial system prompt
      [user]      "Here is the template..."
      [asst]      <full template JSON>
      [user]      "Variables to bake into every string:"
      [asst]      <variables JSON>
      [user]      "Produce the structured session state per the schema."
    """
    provider_name = settings.get("provider", "llama-server")
    initial_system = effective_prompt("meta_initial", settings, provider_name)
    messages: list[dict] = [{"role": "system", "content": initial_system}]

    messages.append({
        "role": "user",
        "content": (
            "Here is the template you must extract structured session state from. "
            "Read every field — characters, scenario, milestones, masked intents, style additions. "
            "After this call, the runtime narrative model will never see this template directly."
        ),
    })
    messages.append({
        "role": "assistant",
        "content": json.dumps(template, indent=2, ensure_ascii=False),
    })
    messages.append({
        "role": "user",
        "content": (
            "Variables to resolve verbatim in every output string. No `{{...}}` reference "
            "should survive into your output:"
        ),
    })
    messages.append({
        "role": "assistant",
        "content": json.dumps(variables or {}, indent=2, ensure_ascii=False),
    })
    messages.append({
        "role": "user",
        "content": (
            "Produce the structured session state per the schema in your system prompt. "
            "Output the JSON object only — no commentary."
        ),
    })
    return messages


def build_meta_analysis_messages(
    *,
    characters: list[dict],
    recent_chunks: list[dict],
    important_facts: list[str],
    meta_prompt: str,
    previous_meta_results: list[dict] | None = None,
    director_note: str | None = None,
) -> list[dict]:
    """Build messages for a regular meta call.

    `director_note` (optional): a free-text hint from the user — typically
    "events look redundant", "milestone X is no longer applicable", or
    "clean up the noise". Triggers cleanup-mode handling per meta.md.
    """
    messages = []

    messages.append({"role": "system", "content": meta_prompt or "You are a narrative analyst. Return only valid JSON."})

    messages.append({
        "role": "user",
        "content": (
            "Here are the current character sheets — full structured state for each character. "
            "Update ONLY characters who appeared in the recent narrative or were affected by it. "
            "For each updated character, your `currentState` REPLACES the existing one; "
            "`traits`, `keyEvents`, and `backstoryAdditions` APPEND new entries; "
            "`identityUpdate`, `voiceUpdate`, `appearanceUpdate` REPLACE those fields when present; "
            "`maskedIntentResolutions` retire intents and integrate them per their `integratesInto` target."
        ),
    })
    messages.append({"role": "assistant", "content": json.dumps(characters, indent=2, ensure_ascii=False)})

    if important_facts:
        messages.append({
            "role": "user",
            "content": (
                "Here is the current facts list. Your `importantFacts` output REPLACES this list entirely — "
                "decide what to KEEP (still relevant), DROP (obsolete or noise), MERGE (redundant variants), "
                "and ADD (truly new). Anything you omit is gone from memory."
            ),
        })
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

    if recent_chunks:
        messages.append({"role": "user", "content": "Here is the recent narrative to analyze:"})
        for chunk in recent_chunks:
            messages.append({"role": "assistant", "content": _get_chunk_narrative(chunk)})

    if director_note:
        messages.append({
            "role": "user",
            "content": (
                "Director cleanup note — treat as a HINT, not a command. Apply your precision rules; "
                "validate before acting:\n\n"
                f"{director_note}\n\n"
                "When cleanup is warranted, your output should be net-shrinking (merge near-duplicate "
                "events, drop traits that restate identity, tighten currentState, drop obvious facts). "
                "If you cannot honestly shrink anything, return mostly empty arrays and one "
                "consistencyFlag explaining that state is already tight."
            ),
        })
    else:
        messages.append({
            "role": "user",
            "content": (
                "Analyze the chunks above. Classify each shift you detect, route to the right field per "
                "the disposition table, apply tier checks, cite the Gap Rule when declining identity or "
                "masked-intent resolution. Be selective — empty arrays are fine."
            ),
        })
    return messages
