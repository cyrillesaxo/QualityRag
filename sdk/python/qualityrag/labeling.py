"""Evidence labeling: turn retrieved passages into gate-ready evidence rows.

The v0.1 gate (``qualityrag.evaluate``) trusts two caller-supplied fields:
``status`` (SUPPORTS / CONTRADICTS / UNKNOWN) and ``origin``. This module
produces ``status`` from text instead of hand labels.

Two labelers are provided:

* ``LexicalLabeler`` - zero-dependency, deterministic baseline. It measures how
  much of a requirement's wording appears in the best-matching sentence and
  flips to CONTRADICTS on a polarity mismatch (negation in the passage but not
  in the claim). It is deliberately simple and is expected to be fooled by
  lexically similar but non-supporting passages; it exists to be beaten.
* ``LLMLabeler`` - provider-agnostic wrapper around any ``complete(prompt)``
  callable. Its output is admitted only when the quoted evidence is an exact
  substring of the passage; anything else fails closed to UNKNOWN.

Every label carries a character span into the passage so an ADMIT can always be
traced to the exact words that justified it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable, Mapping, Protocol

STATUSES = ("SUPPORTS", "CONTRADICTS", "UNKNOWN")

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENTENCE = re.compile(r"[^.!?;\n]+[.!?;]?")
_STOP = frozenset(
    "a an the is are was were be been being am and or but if then than to of in on at by for "
    "from with as it its this that these those there their they them he she his her we our you "
    "your i me my do does did doing done can could would should will shall may might must have has "
    "had having what which who whom whose when where why how so such into onto over under about "
    "after before during while also any all each some more most other only own same very just "
    "per via up down out off again further once here both few nor too s t".split()
)
_NEGATION = re.compile(
    r"\b(not|no|never|none|neither|nor|cannot|can't|won't|don't|doesn't|didn't|isn't|aren't|"
    r"wasn't|weren't|shouldn't|mustn't|prohibit\w*|forbid\w*|forbidden|disallow\w*|bar(?:s|red)?)\b"
)
_QUALIFIER = re.compile(r"\b(unless|only|except|provided that|subject to|conditional)\b")


def _stem(word: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)] + ("y" if suffix in ("ies", "ied") else "")
    return word


def content_terms(text: str) -> set[str]:
    """Lower-cased, stop-word-free, lightly stemmed terms."""
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


@dataclass(frozen=True)
class Label:
    status: str
    span: tuple[int, int] | None = None
    quote: str = ""
    score: float = 0.0
    labeler: str = ""
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["span"] = list(self.span) if self.span else None
        d["reasons"] = list(self.reasons)
        return d


@dataclass(frozen=True)
class Requirement:
    """What the passage must establish. ``kind`` is "claim" or "question"."""
    id: str
    text: str
    kind: str = "claim"


class Labeler(Protocol):
    name: str

    def label(self, requirement: Requirement, passage: str) -> Label: ...


def _sentences(passage: str) -> list[tuple[int, int, str]]:
    out = []
    for m in _SENTENCE.finditer(passage):
        raw = m.group(0)
        lead = len(raw) - len(raw.lstrip())
        text = raw.strip()
        if text:
            start = m.start() + lead
            out.append((start, start + len(text), text))
    return out


class LexicalLabeler:
    """Deterministic overlap + polarity baseline. Not a semantic judge."""

    def __init__(self, support_threshold: float = 0.6, window: int = 2):
        if not 0 < support_threshold <= 1:
            raise ValueError("support_threshold must be in (0, 1]")
        if window < 1:
            raise ValueError("window must be >= 1")
        self.support_threshold = support_threshold
        self.window = window
        self.name = f"lexical@{support_threshold:g}"

    def label(self, requirement: Requirement, passage: str) -> Label:
        need = content_terms(requirement.text)
        if not need:
            return Label("UNKNOWN", labeler=self.name, reasons=("EMPTY_REQUIREMENT",))
        sentences = _sentences(passage)
        best: tuple[float, int, int] | None = None
        # score windows of up to `window` consecutive sentences, prefer shortest on ties
        for i in range(len(sentences)):
            for j in range(i, min(i + self.window, len(sentences))):
                have = content_terms(" ".join(s[2] for s in sentences[i : j + 1]))
                score = len(need & have) / len(need)
                if best is None or score > best[0] + 1e-9:
                    best = (score, i, j)
        if best is None:
            return Label("UNKNOWN", labeler=self.name, reasons=("EMPTY_PASSAGE",))
        score, i, j = best
        start, end = sentences[i][0], sentences[j][1]
        quote = passage[start:end]
        reasons = []
        if _QUALIFIER.search(quote.lower()):
            reasons.append("QUALIFIED")
        if score < self.support_threshold:
            reasons.append("LOW_COVERAGE")
            return Label("UNKNOWN", (start, end), quote, round(score, 4), self.name, tuple(reasons))
        claim_negated = bool(_NEGATION.search(requirement.text.lower()))
        passage_negated = bool(_NEGATION.search(quote.lower()))
        if requirement.kind == "claim" and claim_negated != passage_negated:
            reasons.append("POLARITY_MISMATCH")
            return Label("CONTRADICTS", (start, end), quote, round(score, 4), self.name, tuple(reasons))
        return Label("SUPPORTS", (start, end), quote, round(score, 4), self.name, tuple(reasons))


_PROMPTS = {
    "claim": (
        "You are checking whether a passage establishes a requirement for a retrieval-augmented "
        "answer.\nRequirement: {text}\n\nPassage:\n<<<\n{passage}\n>>>\n\n"
        "Answer SUPPORTS only if the passage itself establishes the requirement, CONTRADICTS if it "
        "establishes the opposite, otherwise UNKNOWN. Background, history, or related facts that do "
        "not establish the requirement are UNKNOWN."
    ),
    "question": (
        "You are checking whether a passage contains the answer to a question.\nQuestion: {text}\n\n"
        "Passage:\n<<<\n{passage}\n>>>\n\n"
        "Answer SUPPORTS only if the passage states the answer, otherwise UNKNOWN. If the passage "
        "is related but does not answer this exact question, answer UNKNOWN."
    ),
}
_JSON_TAIL = (
    '\n\nRespond with JSON only: {{"status": "SUPPORTS"|"CONTRADICTS"|"UNKNOWN", '
    '"quote": "<the shortest exact substring of the passage that justifies the status, or empty>"}}'
)
_JSON_OBJECT = re.compile(r"\{.*\}", re.S)


def _locate(passage: str, quote: str) -> tuple[int, int] | None:
    if not quote:
        return None
    idx = passage.find(quote)
    if idx >= 0:
        return idx, idx + len(quote)
    # tolerate whitespace differences only
    pattern = r"\s+".join(re.escape(part) for part in quote.split())
    m = re.search(pattern, passage) if pattern else None
    return (m.start(), m.end()) if m else None


class LLMLabeler:
    """Wraps ``complete(prompt) -> str``. Fails closed on any malformed or ungrounded output."""

    def __init__(self, complete: Callable[[str], str], name: str = "llm"):
        self.complete = complete
        self.name = name

    def label(self, requirement: Requirement, passage: str) -> Label:
        template = _PROMPTS.get(requirement.kind, _PROMPTS["claim"]) + _JSON_TAIL
        prompt = template.format(text=requirement.text, passage=passage)
        try:
            raw = self.complete(prompt)
        except Exception as exc:  # network, quota, auth: never admit on failure
            return Label("UNKNOWN", labeler=self.name, reasons=("LABELER_ERROR", type(exc).__name__))
        m = _JSON_OBJECT.search(raw or "")
        try:
            data = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict) or data.get("status") not in STATUSES:
            return Label("UNKNOWN", labeler=self.name, reasons=("MALFORMED_OUTPUT",))
        status, quote = data["status"], data.get("quote") or ""
        if not isinstance(quote, str):
            return Label("UNKNOWN", labeler=self.name, reasons=("MALFORMED_OUTPUT",))
        if status == "UNKNOWN":
            return Label("UNKNOWN", labeler=self.name, reasons=("MODEL_UNKNOWN",))
        span = _locate(passage, quote)
        if span is None:
            return Label("UNKNOWN", labeler=self.name, reasons=("UNGROUNDED_QUOTE",))
        return Label(status, span, passage[span[0] : span[1]], 1.0, self.name)


def anthropic_completer(model: str | None = None, max_tokens: int = 300, client: Any = None) -> Callable[[str], str]:
    """Build a ``complete`` callable using the ``anthropic`` SDK (optional dependency).

    Reads ANTHROPIC_API_KEY from the environment unless a client is supplied. The model
    defaults to $QUALITYRAG_LLM_MODEL or ``claude-sonnet-5-5``.
    """
    import os

    if client is None:
        import anthropic  # optional

        client = anthropic.Anthropic()
    model = model or os.environ.get("QUALITYRAG_LLM_MODEL", "claude-sonnet-5-5")

    def complete(prompt: str) -> str:
        msg = client.messages.create(
            model=model, max_tokens=max_tokens, temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(block, "text", "") for block in msg.content)

    return complete


def as_requirements(claims: Mapping[str, Any]) -> list[Requirement]:
    """Accept ``{requirement_id: text}`` or ``{requirement_id: {"text":..., "kind":...}}``."""
    out = []
    for rid, value in claims.items():
        if isinstance(value, str):
            out.append(Requirement(rid, value))
        elif isinstance(value, Mapping) and isinstance(value.get("text"), str):
            out.append(Requirement(rid, value["text"], value.get("kind", "claim")))
        else:
            raise ValueError(f"invalid claim for requirement {rid!r}")
    return out


def label_evidence(
    pack: Mapping[str, Any],
    claims: Mapping[str, Any],
    passages: Iterable[Mapping[str, Any]],
    labeler: Labeler,
    observed_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Label every (passage, requirement) pair.

    ``passages`` items need ``id``, ``text``, ``origin`` and ``source_ref``; an item may carry its
    own ``observed_at``. Returns ``(evidence, trace)``: ``evidence`` holds schema-clean rows for
    ``evaluate`` (SUPPORTS/CONTRADICTS only); ``trace`` holds every label with its span.
    Requirements in the pack without a claim are left unlabeled and therefore stay INCONCLUSIVE.
    """
    pack_ids = {r["id"] for r in pack.get("requirements", [])}
    reqs = [r for r in as_requirements(claims) if r.id in pack_ids]
    evidence, trace = [], []
    for p in passages:
        for key in ("id", "text", "origin", "source_ref"):
            if not isinstance(p.get(key), str) or not p.get(key):
                raise ValueError(f"passage missing {key!r}")
        for req in reqs:
            lab = labeler.label(req, p["text"])
            trace.append({"passage_id": p["id"], "requirement_id": req.id, **lab.to_dict()})
            if lab.status == "UNKNOWN":
                continue
            evidence.append({
                "id": f"{p['id']}::{req.id}",
                "requirement_id": req.id,
                "origin": p["origin"],
                "source_ref": p["source_ref"],
                "status": lab.status,
                "observed_at": p.get("observed_at", observed_at),
            })
    return evidence, trace


def assess(
    pack: Mapping[str, Any],
    claims: Mapping[str, Any],
    passages: Iterable[Mapping[str, Any]],
    labeler: Labeler,
    *,
    as_of: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Label passages, run the gate, and attach the label trace to the result."""
    from . import evaluate

    evidence, trace = label_evidence(pack, claims, list(passages), labeler, observed_at or as_of)
    result = evaluate(dict(pack), evidence, as_of=as_of)
    result["labeler"] = labeler.name
    result["label_trace"] = trace
    return result
