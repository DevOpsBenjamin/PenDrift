## Context Flow (Title)
1. **System**: The prompt above.
2. **User**: "Here is the chapter context (Start, Middle, End) and meta summary..."
3. **Assistant**: [Suggests title].

### GBNF Grammar (Title)
```gbnf
root ::= "{" (
  "\"thinking\":" string ","
  "\"title\":" string
) "}"
```

### JSON Schema (Title)
```json
{
  "type": "object",
  "properties": {
    "thinking": { "type": "string" },
    "title": { "type": "string" }
  },
  "required": ["thinking", "title"],
  "additionalProperties": false
}
```

---

# Consolidation Prompt (kind: consolidate)

...

## Context Flow (Consolidate)
1. **System**: The prompt above.
2. **User**: "Here is the data to consolidate..."
3. **Assistant**: [Compressed JSON].

### GBNF Grammar (Consolidate)
```gbnf
root ::= "{" (
  "\"thinking\":" string ","
  "\"characterUpdates\":" char-updates ","
  "\"importantFacts\":" string-array
) "}"
```

### JSON Schema (Consolidate)
```json
{
  "type": "object",
  "properties": {
    "thinking": { "type": "string" },
    "characterUpdates": { "type": "array", "items": { "type": "object" } },
    "importantFacts": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["thinking", "characterUpdates", "importantFacts"],
  "additionalProperties": false
}
```

