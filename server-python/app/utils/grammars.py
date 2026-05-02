"""GBNF grammars for structured LLM output.

All LLM calls use grammar-constrained JSON output so we never need to
guess/extract JSON from free-form text. Every grammar has a leading
`thinking` field so reasoning models have a dedicated place to reason
in without polluting the payload.

Important: structural whitespace is FORBIDDEN. The grammars produce
compact JSON with no spaces/newlines between tokens. This makes the
streaming parser reliable: it scans the buffer for fixed marker strings
like `"thinking":"` to detect field boundaries — any whitespace would
break the marker match. (Whitespace INSIDE string values is fine and
expected — that's just narrative content.)

Note on GBNF formatting: llama.cpp's grammar parser does not skip newlines
inside a rule body at the top level — continuations only work inside `(...)`
groups (which enable "nested" parsing). So multi-line rule bodies wrap their
content in parens.
"""

_SHARED = r'''
string-array ::= "[]" | "[" string ( "," string )* "]"

string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\\x00-\x1f] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex    ::= [0-9a-fA-F]
'''


# ── Narrative generation ────────────────────────────────
NARRATIVE_GRAMMAR = r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"type\":" response-type ","
  "\"narrative\":" string ","
  "\"suggestions\":" suggestions
) "}"

response-type ::= "\"narrative\"" | "\"suggestion\""
suggestions ::= "[]" | "[" string ( "," string )* "]"
''' + _SHARED


# ── Meta-analysis ───────────────────────────────────────
META_GRAMMAR = r'''
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
''' + _SHARED


# ── Chapter title generation ────────────────────────────
TITLE_GRAMMAR = r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"title\":" string
) "}"
''' + _SHARED


# ── Consolidation (characters + facts compression) ──────
CONSOLIDATE_GRAMMAR = r'''
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
''' + _SHARED


# ── Story consultant Q&A ────────────────────────────────
# Used for "Ask the Narrator" — the LLM has full session context (chars,
# facts, masked intents, recent chunks) and answers analytically rather than
# producing narrative.
QUERY_GRAMMAR = r'''
root ::= "{" (
  "\"thinking\":" string ","
  "\"answer\":" string
) "}"
''' + _SHARED


# ── Chub/TavernAI card → PenDrift template ──────────────
TEMPLATE_GRAMMAR = r'''
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
''' + _SHARED
