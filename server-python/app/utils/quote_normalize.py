"""Normalize typographic quote variants to ASCII straight quotes.

PenDrift's narrative renderer expects ASCII straight quotes:
- `"` (U+0022) for speech / quoted phrases
- `'` (U+0027) for contractions only

Models — especially Grok in French — sometimes emit guillemets `« »`, smart
quotes, or wrap phrases in paired single quotes. Once those land in stored
data (templates, character states, facts), every subsequent prompt re-feeds
them to the model, reinforcing the bad pattern. This helper sanitizes a
string conservatively: no false positives on legitimate apostrophes
(`it's`, `J'ai`, `Tiffany's`).
"""
from __future__ import annotations

import re

# Variant → ASCII replacements applied in order.
_GUILLEMET_OPEN = re.compile(r"«\s*")
_GUILLEMET_CLOSE = re.compile(r"\s*»")
_SMART_DOUBLE = re.compile(r"[“”]")
_SMART_SINGLE = re.compile(r"[‘’]")

# Match a paired ASCII single-quote wrapping a phrase. Designed to spare
# contractions: the lookbehind/lookahead require non-alphanumeric on the
# outside of the pair, so `it's`, `J'ai`, `Tiffany's`, `'s` etc. are skipped.
# Inside the pair: first/last char cannot be whitespace or another quote.
_PAIRED_SINGLES = re.compile(
    r"(?<![A-Za-z0-9])'([^'\s][^']*?[^'\s])'(?![A-Za-z0-9])"
)


def normalize_quotes(s: str | None) -> str:
    """Return `s` with non-ASCII / mis-paired quote variants normalized.
    Returns input unchanged if not a non-empty string."""
    if not isinstance(s, str) or not s:
        return s
    s = _GUILLEMET_OPEN.sub('"', s)
    s = _GUILLEMET_CLOSE.sub('"', s)
    s = _SMART_DOUBLE.sub('"', s)
    s = _SMART_SINGLE.sub("'", s)
    s = _PAIRED_SINGLES.sub(r'"\1"', s)
    return s
