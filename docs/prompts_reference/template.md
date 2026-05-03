## Context Flow (Full Request Structure)

Template generation occurs in three modes:

### 1. Fresh Import (kind: template)
1.  **System**: The `template` prompt.
2.  **User**: "Here is the character card to convert:\n\n[Full Source Text]"

### 2. Rerun (kind: rerun)
1.  **System**: The `rerun` prompt.
2.  **User**: "Here is the character card to convert:\n\n[Full Source Text]"

### 3. Enrich / Editing Pass (kind: enrich)
1.  **System**: The `enrich` prompt.
2.  **User**: "ORIGINAL CARD:\n\n[Full Source Text]"
3.  **User**: "CURRENT TEMPLATE (to be improved):\n\n[JSON of current template]"

---

## Current Default Prompt (llama-server)

```markdown
You are a PenDrift template architect. Your job is to analyze a character card and convert it into a PenDrift "Template" — a structured JSON object that captures the narrative essence of the character and their world.

## PenDrift Concepts

- **Scenario**: A high-level description of the starting situation and character dynamics.
- **Masked Intents**: The character's hidden goals, conditional triggers, or psychological drivers. These are invisible to the reader but guide the LLM.
- **Story Milestones**: Key narrative waypoints the story could progress through (Setup, Escalation, Climax).
- **System Prompt Additions**: Specific style or tone instructions derived from the card.

## Instructions

- BE EXHAUSTIVE. Extract every meaningful detail (traits, verbal tics, relationships).
- Use variables ({{user}}, {{char}}) for flexibility.
- DO NOT EUPHEMIZE. Preserve exact labels and specificity from the source.
- Return ONLY the JSON object.
```

## Output Constraints

### GBNF Grammar
```gbnf
root ::= "{" (
  "\"thinking\":" string ","
  "\"name\":" string ","
  "\"description\":" string ","
  "\"variables\":" variables ","
  "\"characters\":" characters ","
  "\"scenario\":" string ","
  "\"milestones\":" string-array ","
  "\"maskedIntents\":" string-array ","
  "\"systemPromptAdditions\":" string
) "}"

characters ::= "[" character ( "," character )* "]"
character  ::= "{" (
  "\"name\":" string ","
  "\"description\":" string ","
  "\"initialState\":" string
) "}"

variables ::= "{" ( var-pair ( "," var-pair )* )? "}"
var-pair  ::= string ":" string

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
    "name": { "type": "string" },
    "description": { "type": "string" },
    "variables": { 
        "type": "object",
        "additionalProperties": { "type": "string" }
    },
    "characters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string" },
          "initialState": { "type": "string" }
        },
        "required": ["name", "description", "initialState"],
        "additionalProperties": false
      }
    },
    "scenario": { "type": "string" },
    "milestones": { "type": "array", "items": { "type": "string" } },
    "maskedIntents": { "type": "array", "items": { "type": "string" } },
    "systemPromptAdditions": { "type": "string" }
  },
  "required": ["thinking", "name", "description", "variables", "characters", "scenario", "milestones", "maskedIntents", "systemPromptAdditions"],
  "additionalProperties": false
}
```

