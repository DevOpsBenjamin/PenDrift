You are merging a NEW character card into an EXISTING PenDrift template that was previously built from a related card. The two cards belong to the same shared universe — different characters, same scenario — and the goal is to ENRICH the template with information from the new card without losing what's already there.

This is a MERGE pass, not a fresh conversion and not a rewrite. The current template is the source of truth for everything that's already correct; the new card is a source of additional / better information about characters and dynamics that the original card couldn't see.

## Goals (in priority order)

1. **MERGE the new card's character into the template's `characters` array.**
   - If the character is already in `characters` (mentioned by the original card without their own card), REPLACE that entry with a richer one built from the new card's `description` / `personality` / `system_prompt` / `first_mes` / `alternate_greetings`. Their own card always knows them better than third-party mentions.
   - If the character isn't in `characters` yet, ADD them.
   - PRESERVE specific narrative-defining details — body hints, kinks, secrets in their past, distinctive quirks, verbal tics, signature objects/habits (a signature drink, a perfume, a scar, a name they insist on being called). Do NOT compress into generic adjectives. *"Reverted to her maiden name and insists on the old married title in public despite the divorce"* is a defining detail; *"proud and controlling"* alone is generic and useless. If the new card has structured sections (Goals / Desires / Likes / Hates / Emotional Cues / Speech Pattern / Background), mine each item — they exist for a reason.
   - Keep `{{user}}` as `{{user}}`.

2. **EXTRACT additional masked intents** that the new card reveals.
   - The new character's OWN goals, desires, fears, secrets, conditional triggers become maskedIntents about that character. A line like *"Goals: (1) maintain authority, (2) prove she can make {{user}} crawl back"* yields TWO distinct intents — do not collapse.
   - The new card often shows the same dynamic from a different angle: jealousies, secrets, attractions, fears that the first card only hinted at. Add these as new entries.
   - **Conditional triggers are CRITICAL.** If the new card says "if X happens, character reacts Y" (e.g., *"praise → softens, preens, almost girlish for a second"*, *"mention of his new flings → voice goes cold"*), encode each as a separate intent with the trigger AND reaction stated explicitly. These are the levers the narrative engine actually uses.
   - DO NOT EUPHEMIZE labels — racism stays racism, cuckolding stays cuckolding, incestuous stays incestuous, netori stays netori.
   - DO NOT soften specificity either. If a source greeting depicts a concrete scene or act, the resulting intent should preserve enough specificity to drive that exact behavior — not just the abstract category. A concrete intent like *"Character A wants {{user}} to do <specific act> to Character B while C is away, then send B back marked"* is far more useful than the abstracted *"Character A has cuckolding fantasies"*. The narrative engine needs the flesh, not just the genre tag.
   - If the new card contradicts an existing intent (e.g., one card says X is in love, the new one says X is faking), merge into a richer intent that captures the truth (e.g., "X feigns affection while actually planning to leave").

3. **ENRICH milestones** with the new card's narrative arc.
   - **The new card's `alternate_greetings` are very likely milestones for that character's POV** — three greetings are usually three timed waypoints along a single arc, not three independent stories. A "first contact" greeting, a "stakes have escalated" greeting, and a "final reckoning" greeting → those are Setup / Escalation / Climax from that character's angle. Add them, even when the template already has milestones from another character's POV. Character-anchored milestones are fine and welcome (e.g., a milestone that frames a specific scheme or pitch one character makes to {{user}} that doesn't fit the existing arc beats).
   - Don't duplicate milestones the template already has — but DO add the new card's distinct moments.

4. **REFINE other characters' entries** when the new card reveals something about them.
   - If the new card describes how the new character SEES another existing character, that view is a relationship dynamic — add it to `maskedIntents`, not to the existing character's `description` (which should describe who they are, not how others see them).

5. **PRESERVE the scenario** unless the new card unambiguously shows it was wrong. If the scenario changes, briefly acknowledge multiple starting points (consistent with how chub_import handles alternate starts).

6. **VERIFY variable substitution** — every declared variable still used everywhere as `{{var_name}}`. If the new card introduces a name worth making variable (e.g., a new character's name that the director might want to swap), declare it AND substitute everywhere.

7. **FLAG cross-card inconsistencies** in your `thinking` when you spot them (e.g., two cards disagree on a last name, an age, who-divorced-whom, ethnicity). Make a deliberate call and note it; don't paper over silently.

## What NOT to do

- Do NOT rewrite the entire template from the new card alone — the new card is one perspective in a shared universe, not the universe itself.
- Do NOT remove characters or intents already in the template just because they're not mentioned in the new card.
- Do NOT downgrade the description of an existing character (e.g., the previous `description` was rich; if the new card has nothing new about them, keep the old description).
- Do NOT duplicate intents in different words.
- Do NOT mix the two cards' system prompts blindly — keep the most useful style instructions, not both stacked.
- Do NOT silently drop source content because it doesn't fit your mental summary. If you considered a detail and chose not to carry it, justify in `thinking`.

## The thinking field (REQUIRED, FIRST, NON-EMPTY)

Audit and explain what you're merging. Be specific:

1. **Who is the new card's main character** — name, role, key traits the template didn't capture.
2. **What's NEW** that the new card provides — quote concrete lines/details, do not paraphrase to nothing.
3. **What overlaps** with content the template already has — explain whether you're keeping the existing version, the new version, or merging both.
4. **What new masked intents** emerge — walk the new card's structured sections (Goals / Desires / Hates / Emotional Cues / Speech Pattern), its relationships, and its conditional triggers. List the intents before writing the JSON.
5. **What new milestones** the new card suggests — explicitly check EACH `alternate_greeting` and decide: is this a new milestone, a duplicate of an existing one, or neither?
6. **What you are explicitly preserving** from the current template because it's already correct.
7. **What source content I considered but did NOT carry forward, and why.** This step is REQUIRED — silent drops are bugs. If you decided not to include a detail, name it and justify (redundant / out of scope / contradicts canon / etc.).
8. **Cross-card inconsistencies** — anything the two cards disagree on, and how you're resolving it.

A minimal thinking ("everything merged fine") almost certainly means you didn't audit. Do the work.

## Output format

Return ONLY valid JSON. Same schema as a fresh import — `thinking` FIRST:

{
  "thinking": "Your merge audit, with concrete findings...",
  "name": "Template display name",
  "description": "1-2 sentence description (may be richer now that you have more characters)",
  "variables": { ... },
  "characters": [
    { "name": "Name", "description": "...", "initialState": "..." }
  ],
  "scenario": "Third-person narrative scenario",
  "milestones": [ "...", "..." ],
  "maskedIntents": [ "...", "..." ],
  "systemPromptAdditions": "Style and tone instructions"
}

## Rules

- Output is the COMPLETE template (every field present), not a diff.
- Keep `{{user}}` as `{{user}}`.
- DO NOT EUPHEMIZE — preserve exact labels from BOTH cards.
- DO NOT soften specificity — preserve concrete acts, gestures, words, and signature details from the source greetings and structured sections.
- Substitute every declared variable EVERYWHERE.
- Output language matches the dominant language across the cards.
