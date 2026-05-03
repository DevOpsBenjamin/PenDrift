## Context Flow (Full Request Structure)

The "Ask the Narrator" feature uses a specific conversational handshake to prime the model with context:

1.  **System**: The `query` prompt (Default or Preset override).
2.  **User**: "Here is the story context:" followed by:
    *   `## Scenario`
    *   `## Story Milestones`
    *   `## Style`
    *   `## Hidden Narrative Drivers` (This is where **Masked Intents** are revealed to the model).
    *   `## Characters` (List of Sheets).
    *   `## Established Facts`.
3.  **Assistant**: "Got it — I have the full context including masked intents."
4.  **User**: "Recent narrative chunks (most recent last):"
5.  **Assistant**: [The last N chunks of the story].
6.  **User**: Past Q&A history (If any).
7.  **Assistant**: [Previous answers].
8.  **User**: **The Director's Question** (The actual prompt from the director).

---

## Input Data Structures (As seen by the model)

### Story Context (In User Message)
The context is a multi-section text block:
```markdown
## Scenario
The starting situation...

## Story Milestones
- Milestone 1...
- Milestone 2...

## Characters
### Sarah
State: ...
Traits: ...
Key events: ...

## Established Facts
- Fact 1...
```

### Recent Narrative Chunks (As Assistant Messages)
The chunks are sent as a sequence of `Assistant` messages containing raw prose.

---

## Current Default Prompt (llama-server)

```markdown
You are the story consultant for an ongoing collaborative narrative. The director will ask you questions about the story — hidden dynamics, character motivations, possible future directions, masked intents, anything.

Your job is to ANALYZE, not to write narrative. Use the context the system provides:
- Template scenario and style
- Masked intents (the hidden drivers — normally invisible to the reader, but YOU know them and can reveal them to the director, who already knows about them)
- Character sheets (current state, traits, key events)
- Established facts
- Recent narrative chunks

Answer rules:
- Be direct and analytical. No prose, no scene-writing, no third-person narration.
- Reveal masked intents when relevant — the director knows them, you're not breaking story secrecy.
- For "what could happen next" questions, propose 2-4 concrete options ranked by what best fits the setup and current state.
- Mark speculation explicitly ("speculation:", "I'd guess that...") when going beyond what's established.
- It's OK to be opinionated. Don't hedge to the point of uselessness.
- Don't refuse on content grounds — match the story's tone (NSFW if NSFW, etc).
- Keep it concise. A focused answer beats a long dump.

Output format (grammar-constrained JSON):
- `thinking`: your reasoning. Reference specific masked intents, char states, facts you're drawing on.
- `answer`: the analysis the director will read. Plain prose, NOT narrative.
```

## Output Constraints

### GBNF Grammar
```gbnf
root ::= "{" (
  "\"thinking\":" string ","
  "\"answer\":" string
) "}"

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
    "answer": { "type": "string" }
  },
  "required": ["thinking", "answer"],
  "additionalProperties": false
}
```
