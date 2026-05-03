## Context Flow (Full Request Structure)

When a narrative chunk is generated, PenDrift builds a single System message by concatenating several sections. All placeholders like `{{user}}` are resolved before being sent.

### 1. The System Message (Concatenated)
The `System` role contains the core context. Sections are added only if they have content:

1.  **Base Instructions**: The default `narrative` prompt (or preset override).
2.  **Scenario**: Added as `## Scenario` followed by the template's scenario text.
3.  **Milestones**: Added as `## Story Milestones (...)` followed by a list of resolved milestones.
4.  **Style Instructions**: Added as `## Style Instructions` followed by `systemPromptAdditions`.
5.  **Hidden Drivers**: Added as `## Hidden Narrative Drivers (...)` followed by `maskedIntents` (resolved).
6.  **Character States**: Added as `## Current Character States`. For each character:
    *   `### [Name]`
    *   `State: [currentState]`
    *   `Traits: [List of traits]`
    *   `Key events: [List of events]`
7.  **Established Facts**: Added as `## Established Facts` followed by a bulleted list.

### 2. Message History
After the System message, PenDrift adds User/Assistant turns:

*   **User**: "Context from the end of the previous chapter:" (If applicable).
*   **Assistant**: [Prose from last 2 chunks of prev chapter].
*   **User**: "Begin."
*   **Assistant**: [The last N chunks from the current chapter].
*   **User**: [Optional] "⚠️ DISCARDED PREVIOUS ATTEMPT..." (Only during manual regen).
*   **User**: **The Directive** (The actual instruction from the director).

---

## Input Data Structures (As seen by the model)

### Character Sheets (In System Prompt)
Characters are rendered as text in the `## Current Character States` section:
```markdown
### Sarah
State: Exhausted but determined, clutching the old key.
Traits: Loyal, observant, secretive.
Key events: Found the cellar key in the library; Discovered Mark's secret letter.
```

### Story Milestones (In System Prompt)
Milestones are a bulleted list:
```markdown
- Sarah reaches the cellar and opens the heavy iron door.
- The confrontation with the hooded figure.
```

### Established Facts (In System Prompt)
Facts are a bulleted list:
```markdown
- The king is dead.
- The cellar key is hidden under the rug.
```

---

## Current Default Prompt (llama-server)

```markdown
You are the narrator for PenDrift, an advanced collaborative fiction engine. Your role is to take the director's instructions and the current story state (characters, facts, context) and produce a high-quality narrative chunk.

### Suggestions

Always propose 2-4 suggestions. They DON'T all need to branch — mix flavors based on the beat:
- **Continue**: "Continue the scene as Sarah inspects the rest of the room."
- **Skip**: "Skip to that evening when Ethan returns home."
- **Branch**: "Sarah decides to confront Mark instead of waiting."

Other valid flavors: deepen the moment, shift POV, insert a small twist. Diversity in FLAVOR matters more than divergent plot. The point is easy steering without writing.

Chunks vary in length — short descriptive chunks are fine, don't artificially stretch.

## Rules
- Third person, past tense by default. Match the established tone.
- Show, don't tell. Dialogue, gestures, atmosphere, sensory details.
- Characters behave per their CURRENT state (in sheets), not their initial description. People change.
- Inner monologue is powerful — what they think vs what they say.
- Never break the fourth wall, never address the director, never add meta-commentary or author's notes.
- Never refuse or hedge. You are the author. Write the scene.
- Never summarize what just happened. Stay in the moment.
- Vague directive -> make bold creative choices. Surprise is good.
- Vary sentence length and structure. Avoid repetitive patterns.
- End at a natural narrative beat — tension, reaction, pause. Not a summary.
```

## Response Format Instructions (Hardcoded for llama-server)

```markdown
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
- If you genuinely cannot think of suggestions, output [].
```

## Output Constraints

### GBNF Grammar
```gbnf
root ::= "{" (
  "\"thinking\":" string ","
  "\"narrative\":" string ","
  "\"suggestions\":" suggestions
) "}"

suggestions ::= "[]" | "[" string ( "," string )* "]"

string-array ::= "[]" | "[" string ( "," string )* "]"
string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\\x00-\x1f] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex    ::= [0-9a-fA-F]
```

### JSON Schema (OpenAI / xAI)
```json
{
  "type": "object",
  "properties": {
    "thinking": { "type": "string" },
    "narrative": { "type": "string" },
    "suggestions": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["thinking", "narrative", "suggestions"],
  "additionalProperties": false
}
```
