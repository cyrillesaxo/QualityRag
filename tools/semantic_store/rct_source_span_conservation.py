"""Source-span semantic conservation checks for explicit reviewed obligations.

This does NOT infer semantic equivalence from text. An external reviewer supplies
a version-bound inventory of source spans and typed distinctions. The verifier
checks exact source/candidate quote bounds, obligatory inventory coverage and
typed literal equality. New or unreviewed meaning => UNKNOWN; missing or changed
reviewed invariants => REFUSE. Even exact equality => INCONCLUSIVE.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from store import digest

SCHEMA = "rct.source-span-conservation/v2.1"
KINDS = frozenset((
    "ACTOR", "RECIPIENT", "NEGATION", "CONDITION", "EXCEPTION",
    "DEADLINE", "NUMBER", "UNIT", "MODALITY", "SCOPE",
    "AUTHORITY", "OBLIGATION", "LEGAL_EFFECT", "TEMPORAL",
))
MAX_DOC_CHARS = 200000
MAX_OBLIGATIONS = 256


def _span(document: str, record: dict, *, side: str) -> str:
    value = record.get(side)
    if not isinstance(value, dict) or set(value) != {"start", "end", "quote"}:
        raise ValueError("Span must provide exact start/end/quote")
    start, end, quote = value["start"], value["end"], value["quote"]
    if (type(start) is not int or type(end) is not int or
            not isinstance(quote, str) or
            not 0 <= start < end <= len(document) or
            document[start:end] != quote):
        raise ValueError("Source-bound quote mismatch")
    return quote


def audit_source_spans(source: str, candidate: str, obligations: list[dict],
                       *, source_digest: str, candidate_digest: str,
                       reviewed_inventory_digest: str) -> dict[str, Any]:
    """Evaluate exact typed spans with explicit review inventory consistency.

    Each obligation:
      {id, kind, required, source:{start,end,quote},
       target:{start,end,quote}|None, expected_value, observed_value}
    Source records are immutable by caller-provided source hash, but no
    cryptographic review signature is claimed here.
    """
    if (not isinstance(source, str) or not isinstance(candidate, str)
            or not 1 <= len(source) <= MAX_DOC_CHARS
            or not 1 <= len(candidate) <= MAX_DOC_CHARS
            or not isinstance(obligations, list)
            or not 1 <= len(obligations) <= MAX_OBLIGATIONS):
        raise ValueError("Bounded nonempty source/candidate and obligations required")
    if (source_digest != sha256(source.encode()).hexdigest()
            or candidate_digest != sha256(candidate.encode()).hexdigest()
            or reviewed_inventory_digest != digest(obligations)):
        raise ValueError("Stale or altered source, candidate or inventory")
    seen, findings, blocked = set(), [], False
    for item in obligations:
        if not isinstance(item, dict) or set(item) != {
                "id", "kind", "required", "source", "target",
                "expected_value", "observed_value"}:
            raise ValueError("Exact typed-obligation schema required")
        oid, kind = item["id"], item["kind"]
        if (not isinstance(oid, str) or not oid or oid in seen
                or kind not in KINDS
                or type(item["required"]) is not bool
                or not isinstance(item["expected_value"], str)
                or not item["expected_value"]):
            raise ValueError("Invalid or duplicate obligation")
        seen.add(oid)
        _span(source, item, side="source")
        target=item["target"]
        observed=item["observed_value"]
        if target is None:
            status = "MISSING_REQUIRED" if item["required"] else "DECLARED_OPTIONAL_OMISSION"
        else:
            _span(candidate, item, side="target")
            if observed is None:
                status = "UNMEASURED"
            elif not isinstance(observed, str):
                raise ValueError("Observed semantic value must be string or null")
            elif observed != item["expected_value"]:
                status = "CONTRADICTED"
            else:
                status = "TYPED_DECLARATION_MATCH"
        if status in ("MISSING_REQUIRED", "CONTRADICTED"):
            blocked=True
        findings.append({
            "id": oid, "kind": kind, "status": status,
            "source_quote_sha256":sha256(item["source"]["quote"].encode()).hexdigest(),
            "target_present": target is not None,
            "independently_verified":False,
        })
    result={
        "schema": SCHEMA,
        "source_sha256":source_digest,"candidate_sha256":candidate_digest,
        "reviewed_inventory_sha256":reviewed_inventory_digest,
        "obligations_checked":len(obligations),
        "findings":findings,
        "verdict":"REFUSE" if blocked else "INCONCLUSIVE",
        "can_generate":False,
        "qualityrag_admission":"INCONCLUSIVE",
        "semantic_completeness":"UNKNOWN",
        "review_authority":"NOT_AUTHENTICATED",
        "boundary":"Typed values and inventory supplied by caller; text meaning not inferred; no unlisted-invariant guarantee",
    }
    result["fingerprint"]=digest(result)
    return result
