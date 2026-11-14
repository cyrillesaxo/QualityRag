"""Deterministic, extractor-independent obligation triggers (US-077).

A versioned lexical inventory marks sentences that may state a constraint. No
model is called. The inventory is incomplete by construction: a constraint with
no lexical marker is a miss, never evidence that no constraint exists. Recall
and false-trigger rate are UNMEASURED until a frozen gold set exists (US-084).
English markers only.
"""
from __future__ import annotations

import re

TRIGGER_SET = "qualityrag.conversation-triggers/v0.1"

_FAMILIES = {
    "EXCEPTION": r"\b(?:except|unless|excluding|other than|but not|apart from|aside from)\b",
    "NEGATION": r"\b(?:not|never|no|none|cannot|without|neither|nor)\b|n't\b",
    "CONDITION": r"\b(?:if|only if|when|whenever|provided that|as long as|in case)\b",
    "DEADLINE": r"\b(?:by|before|until|no later than|deadline|due|within \d+)\b",
    "NUMBER_UNIT": r"\d+(?:[.,]\d+)*\s?(?:%|[A-Za-z]{1,12}\b)?",
    "MODALITY": r"\b(?:must|shall|should|may|required|need to|needs to|have to|has to|always|only)\b",
    "BACK_REFERENCE": r"\b(?:as i said|as mentioned|earlier|above|previously|the same|again)\b",
    "SUPERSESSION": r"\b(?:instead|actually|from now on|no longer|scratch that|rather than|forget (?:that|the))\b",
}
_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in _FAMILIES.items()}

# Families whose presence makes a user sentence a critical obligation candidate.
CRITICAL_FAMILIES = frozenset(
    ("EXCEPTION", "NEGATION", "CONDITION", "DEADLINE", "NUMBER_UNIT", "MODALITY"))

# A boundary is sentence punctuation (a full stop between digits is not one) or a line break.
_BOUNDARY = re.compile(r"(?:[!?]|\.(?!\d))+\s*|\n+")

MAX_CHARS = 200_000


def segments(text):
    """Partition ``text`` into contiguous, non-empty, non-overlapping spans covering all of it."""
    if not isinstance(text, str) or len(text) > MAX_CHARS:
        raise ValueError("Bounded text required")
    out, start = [], 0
    for match in _BOUNDARY.finditer(text):
        if match.end() > start:
            out.append((start, match.end()))
            start = match.end()
    if start < len(text):
        out.append((start, len(text)))
    return out


def families(sentence):
    """Sorted trigger families present in one sentence."""
    return sorted(name for name, pattern in _COMPILED.items() if pattern.search(sentence))


def scan(text):
    """Every span of ``text`` with the trigger families it contains (possibly none)."""
    return [{"start": start, "end": end, "families": families(text[start:end])}
            for start, end in segments(text)]
