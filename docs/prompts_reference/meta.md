## Context Flow (Full Request Structure)

The meta-analysis runs in the background. It uses a sequence of context-injection messages:

1.  **System**: The effective `meta` prompt (Default or Preset override).
2.  **User**: "Here are the current character sheets. Update ONLY characters who appeared..."
3.  **Assistant**: [Full JSON list of current character sheets].
4.  **User**: "Here is the current facts list. Your `importantFacts` output REPLACES this list..." (Only if facts exist).
5.  **Assistant**: [Bullet-point list of current facts].
6.  **User**: [Optional] Summary of previous analysis results (If continuity is needed).
7.  **User**: "Here is the recent narrative to analyze:"
8.  **Assistant**: [The specific narrative chunks that were just written/edited].
9.  **User**: "Analyze the narrative above. Update only characters who appeared, detect genuinely new ones, flag concrete contradictions, and emit the new facts list..."

---

## Input Data Structures (As seen by the model)

### Character Sheets (JSON)
The model receives the full list of characters as a JSON array in an `Assistant` message:
```json
[
  {
    "name": "Sarah",
    "currentState": "Exhausted but determined, clutching the old key.",
    "traits": ["Loyal", "observant", "secretive"],
    "keyEvents": ["Found the cellar key in the library", "Discovered Mark's secret letter"]
  }
]
```

### Established Facts (Text List)
Facts are sent as a bulleted text list in an `Assistant` message:
```markdown
- The king is dead.
- The cellar key is hidden under the rug.
```

---

## Current Default Prompt (llama-server)

```markdown
You are a narrative analyst. Your job is to listen to a narrative excerpt and update the "Character Sheets" and "Established Facts" to reflect the new state of the story.

Character sheets represent the CURRENT state of a character (where they are, what they're wearing, how they feel, what they know). 

Established Facts are global truth values about the world or the plot (e.g., "The king is dead", "The cellar key is hidden under the rug").

## Instructions

- BE SELECTIVE. Not every chunk needs a character update or a new fact.
- Only update characters who actually APPEARED or were significantly referenced.
- Keep traits behavioral and psychological. Physical state (wounds, clothes) goes in `currentState`.
- Merge facts aggressively. 
- Use the `thinking` field to justify your changes.
```

## Output Constraints

### GBNF Grammar
```gbnf
root ::= "{" (
  "\"thinking\":" string ","
  "\"characterUpdates\":" char-updates ","
  "\"newCharacters\":" char-updates ","
  "\"consistencyFlags\":" string-array ","
  "\"importantFacts\":" string-array
) "}"

char-updates ::= "[]" | "[" char-update ( "," char-update )* "]"
char-update  ::= "{" (
  "\"name\":" string ","
  "\"currentState\":" string ","
  "\"traits\":" string-array ","
  "\"keyEvents\":" string-array
) "}"

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
    "characterUpdates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "currentState": { "type": "string" },
          "traits": { "type": "array", "items": { "type": "string" } },
          "keyEvents": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["name", "currentState", "traits", "keyEvents"],
        "additionalProperties": false
      }
    },
    "newCharacters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "currentState": { "type": "string" },
          "traits": { "type": "array", "items": { "type": "string" } },
          "keyEvents": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["name", "currentState", "traits", "keyEvents"],
        "additionalProperties": false
      }
    },
    "consistencyFlags": { "type": "array", "items": { "type": "string" } },
    "importantFacts": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["thinking", "characterUpdates", "newCharacters", "consistencyFlags", "importantFacts"],
  "additionalProperties": false
}
```
