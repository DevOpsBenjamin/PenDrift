"""GBNF grammars for structured LLM output."""

# ── Narrative generation grammar ────────────────────────
# Forces the model to output structured JSON:
# {
#   "thinking": "reasoning and planning...",
#   "type": "narrative" | "suggestion",
#   "narrative": "the prose...",
#   "suggestions": ["option 1", "option 2"] | []
# }
#
# The model gets a global max_tokens budget and distributes it
# across fields. The grammar guarantees valid JSON even if
# max_tokens cuts off — llama.cpp will complete closing tokens.

NARRATIVE_GRAMMAR = r'''
root ::= "{" ws
  "\"thinking\"" ws ":" ws string "," ws
  "\"type\"" ws ":" ws response-type "," ws
  "\"narrative\"" ws ":" ws string "," ws
  "\"suggestions\"" ws ":" ws suggestions
  ws "}"

response-type ::= "\"narrative\"" | "\"suggestion\""

suggestions ::= "[]" | "[" ws string ( "," ws string )* ws "]"

string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\\x00-\x1f] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex    ::= [0-9a-fA-F]

ws ::= [ \t\n\r]*
'''

# ── Meta-analysis grammar ───────────────────────────────
# Forces valid JSON for character updates, facts, etc.

META_GRAMMAR = r'''
root ::= "{" ws
  "\"thinking\"" ws ":" ws string "," ws
  "\"characterUpdates\"" ws ":" ws char-updates "," ws
  "\"newCharacters\"" ws ":" ws char-updates "," ws
  "\"consistencyFlags\"" ws ":" ws string-array "," ws
  "\"importantFacts\"" ws ":" ws string-array
  ws "}"

char-updates ::= "[]" | "[" ws char-update ( "," ws char-update )* ws "]"
char-update  ::= "{" ws
  "\"name\"" ws ":" ws string "," ws
  "\"currentState\"" ws ":" ws string "," ws
  "\"traits\"" ws ":" ws string-array "," ws
  "\"keyEvents\"" ws ":" ws string-array
  ws "}"

string-array ::= "[]" | "[" ws string ( "," ws string )* ws "]"

string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\\x00-\x1f] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex    ::= [0-9a-fA-F]

ws ::= [ \t\n\r]*
'''
