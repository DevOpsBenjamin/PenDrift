"""Registry of structured output definitions (GBNF grammars and JSON Schemas).

This allows the LLM providers to choose the format they support based on the
high-level 'kind' of task being performed.
"""

# GBNF Shared rules
_SHARED_GBNF = r'''
string-array ::= "[]" | "[" string ( "," string )* "]"

string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\\x00-\x1f] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex    ::= [0-9a-fA-F]
'''

# ── Registry ────────────────────────────────────────────

STRUCTURED_OUTPUTS = {
    "narrative": {
        "gbnf": r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"narrative\":" string ","
  "\"suggestions\":" suggestions
) "}"

suggestions ::= "[]" | "[" string ( "," string )* "]"
''' + _SHARED_GBNF,
        "json_schema": {
            "type": "object",
            "properties": {
                "thinking": { "type": "string" },
                "narrative": { "type": "string" },
                "suggestions": { "type": "array", "items": { "type": "string" } }
            },
            "required": ["thinking", "narrative", "suggestions"],
            "additionalProperties": False
        }
    },

    "meta": {
        "gbnf": r'''
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
''' + _SHARED_GBNF,
        "json_schema": {
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
                        "additionalProperties": False
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
                        "additionalProperties": False
                    }
                },
                "consistencyFlags": { "type": "array", "items": { "type": "string" } },
                "importantFacts": { "type": "array", "items": { "type": "string" } }
            },
            "required": ["thinking", "characterUpdates", "newCharacters", "consistencyFlags", "importantFacts"],
            "additionalProperties": False
        }
    },

    "title": {
        "gbnf": r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"title\":" string
) "}"
''' + _SHARED_GBNF,
        "json_schema": {
            "type": "object",
            "properties": {
                "thinking": { "type": "string" },
                "title": { "type": "string" }
            },
            "required": ["thinking", "title"],
            "additionalProperties": False
        }
    },

    "query": {
        "gbnf": r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"answer\":" string
) "}"
''' + _SHARED_GBNF,
        "json_schema": {
            "type": "object",
            "properties": {
                "thinking": { "type": "string" },
                "answer": { "type": "string" }
            },
            "required": ["thinking", "answer"],
            "additionalProperties": False
        }
    },

    "consolidate": {
        "gbnf": r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"characters\":" char-array ","
  "\"facts\":" string-array
) "}"

char-array ::= "[]" | "[" character ( "," character )* "]"
character ::= "{" (
  "\"name\":" string ","
  "\"currentState\":" string ","
  "\"traits\":" string-array ","
  "\"keyEvents\":" string-array
) "}"
''' + _SHARED_GBNF,
        "json_schema": {
            "type": "object",
            "properties": {
                "thinking": { "type": "string" },
                "characters": {
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
                        "additionalProperties": False
                    }
                },
                "facts": { "type": "array", "items": { "type": "string" } }
            },
            "required": ["thinking", "characters", "facts"],
            "additionalProperties": False
        }
    },

    "template": {
        "gbnf": r'''
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
''' + _SHARED_GBNF,
        "json_schema": {
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
                        "additionalProperties": False
                    }
                },
                "scenario": { "type": "string" },
                "milestones": { "type": "array", "items": { "type": "string" } },
                "maskedIntents": { "type": "array", "items": { "type": "string" } },
                "systemPromptAdditions": { "type": "string" }
            },
            "required": [
                "thinking", "name", "description", "variables", "characters",
                "scenario", "milestones", "maskedIntents", "systemPromptAdditions"
            ],
            "additionalProperties": False,
            "strict": False
        }
    }
}


# Alias kinds that share an existing structured output. Lets callers pass
# the kind that matches their flow (e.g., "enrich") and still get the right
# grammar / schema injected by the provider.
_ALIASES = {
    "chub-import": "template",
    "enrich": "template",
    "rerun": "template",
    "narrative-stream": "narrative",
    "query-stream": "query",
}
for alias, target in _ALIASES.items():
    STRUCTURED_OUTPUTS[alias] = STRUCTURED_OUTPUTS[target]
