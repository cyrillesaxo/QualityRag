"""Deterministic three-way turn classification with fail-to-fork (US-072).

Verdicts: REFINE, AMBIGUOUS, PIVOT. Only explicit lexical evidence yields REFINE
or PIVOT; everything else, including any error, is AMBIGUOUS, which forks.
Accuracy is UNMEASURED until scored on a frozen human-labelled set (US-084).
The classifier never grades itself. English markers only.
"""
from __future__ import annotations

import re

CLASSIFIER = "qualityrag.conversation-classifier/v0.1"
THRESHOLDS = {"overlap_high": 0.5, "overlap_low": 0.1, "short_turn_tokens": 8}

_TOKEN = re.compile(r"[A-Za-z0-9]{3,}")
_STOP = frozenset((
    "the and for that this with you your are was were have has had not but can will "
    "would should could from they them what when where which how why who its into about "
    "please just also then than there here make made does did").split())
_BACK = re.compile(
    r"\b(?:as i said|as mentioned|earlier|above|previous(?:ly)?|the same|again|instead|"
    r"actually|from now on|make it|change (?:it|that|the)|shorter|longer|simpler|rename|"
    r"fix (?:it|that|the)|update (?:it|that|the)|continue|keep (?:it|the)|add (?:to|a|an|the)|"
    r"remove (?:it|that|the))\b", re.IGNORECASE)
_PIVOT = re.compile(
    r"\b(?:new topic|unrelated|different (?:question|topic|subject)|separately|"
    r"by the way|switching (?:topic|gears)|on another note|change of subject)\b", re.IGNORECASE)


def _tokens(text):
    return {t.lower() for t in _TOKEN.findall(text)} - _STOP


def classify(turn_text, context_text):
    """Classify a new user turn against the branch context it follows."""
    try:
        if not isinstance(turn_text, str) or not isinstance(context_text, str):
            raise ValueError("text required")
        turn, context = _tokens(turn_text), _tokens(context_text)
        overlap = len(turn & context) / len(turn) if turn else 0.0
        back = bool(_BACK.search(turn_text))
        pivot = bool(_PIVOT.search(turn_text))
        short = len(turn_text.split()) <= THRESHOLDS["short_turn_tokens"]
        if pivot and not back and overlap < THRESHOLDS["overlap_low"]:
            verdict = "PIVOT"
        elif not pivot and back and (short or overlap >= THRESHOLDS["overlap_low"]):
            verdict = "REFINE"
        elif not pivot and overlap >= THRESHOLDS["overlap_high"]:
            verdict = "REFINE"
        else:
            verdict = "AMBIGUOUS"
        features = {"overlap": round(overlap, 4), "back_reference": back,
                    "pivot_marker": pivot, "short_turn": short}
    except Exception as exc:  # fail to fork, never to a silent refine or pivot
        verdict, features = "AMBIGUOUS", {"error": type(exc).__name__}
    return {"verdict": verdict, "features": features, "classifier": CLASSIFIER,
            "thresholds": dict(THRESHOLDS), "accuracy": "UNMEASURED"}
