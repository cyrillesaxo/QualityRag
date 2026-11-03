"""Conservative deterministic checks over explicitly supplied timestamp/value observations.

This runtime NEVER invokes arbitrary predicates, probes or external tools.
It neither authenticates observations nor establishes source correctness.
Unsupported IR kinds remain INCONCLUSIVE; failed checks become REFUSE.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from typed_ir import IR_SCHEMA, _fingerprint

RESULT_SCHEMA = "qualityrag.semantic-check-result/v1"
MAX_NODES = 240


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 45:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _event(events: dict, name: str) -> datetime | None:
    record = events.get(name)
    if not isinstance(record, dict) or not isinstance(record.get("source_ref"), str) or not record["source_ref"].strip():
        return None
    return _instant(record.get("at"))


def _temporal(node: dict, events: dict, as_of: datetime | None) -> tuple[str, str]:
    p = node.get("parameters", {})
    if node.get("runtime") != "BOUNDED_TEMPORAL_V0_1" or node.get("status") != "EVALUABLE":
        return "INCONCLUSIVE", "TEMPORAL_NOT_BOUND"
    if not isinstance(p, dict):
        return "INCONCLUSIVE", "INVALID_TEMPORAL_SPEC"
    anchor = _event(events, p.get("anchor", ""))
    if anchor is None:
        return "INCONCLUSIVE", "MISSING_OR_INVALID_ANCHOR"
    relation = p.get("relation")
    if relation == "EXPIRES_AT":
        if as_of is None:
            return "INCONCLUSIVE", "INVALID_AS_OF"
        return ("ADMIT", "WITHIN_EXPIRY") if as_of < anchor else ("REFUSE", "EXPIRED_OR_AT_EXPIRY")
    subject = _event(events, p.get("subject", ""))
    if subject is None:
        return "INCONCLUSIVE", "MISSING_OR_INVALID_SUBJECT"
    delta = (subject - anchor).total_seconds()
    if relation == "AFTER":
        return ("ADMIT", "AFTER_CONFIRMED") if delta > 0 else ("REFUSE", "NOT_AFTER")
    if relation == "BEFORE":
        return ("ADMIT", "BEFORE_CONFIRMED") if delta < 0 else ("REFUSE", "NOT_BEFORE")
    if relation == "WITHIN":
        limit = p.get("duration_seconds")
        if type(limit) is not int or not 1 <= limit <= 31_536_000:
            return "INCONCLUSIVE", "INVALID_INTERVAL"
        return ("ADMIT", "ORDERED_WITHIN_INTERVAL") if 0 <= delta <= limit else ("REFUSE", "OUTSIDE_INTERVAL")
    return "INCONCLUSIVE", "UNSUPPORTED_RELATION"


def _probe(node: dict, probes: dict) -> tuple[str, str]:
    p = node.get("parameters", {})
    if node.get("runtime") != "BOUNDED_PROBE_V0_1" or node.get("status") != "EVALUABLE":
        return "INCONCLUSIVE", "PROBE_NOT_BOUND"
    if not isinstance(p, dict):
        return "INCONCLUSIVE", "INVALID_PROBE_SPEC"
    receipt = probes.get(p.get("probe_id", ""))
    if not isinstance(receipt, dict) or not isinstance(receipt.get("source_ref"), str) or not receipt["source_ref"].strip():
        return "INCONCLUSIVE", "MISSING_PROBE_RECEIPT"
    if receipt.get("artifact_type") != p.get("artifact_type"):
        return "INCONCLUSIVE", "ARTIFACT_TYPE_MISMATCH"
    fields = receipt.get("values")
    if not isinstance(fields, dict) or p.get("field") not in fields:
        return "INCONCLUSIVE", "MISSING_OBSERVATION_FIELD"
    value = fields[p["field"]]
    if p.get("check") == "EQUALS":
        expected = p.get("expected")
        if type(value) is not type(expected):
            return "INCONCLUSIVE", "VALUE_TYPE_MISMATCH"
        if isinstance(value, float) and not isfinite(value):
            return "INCONCLUSIVE", "NONFINITE_OBSERVATION"
        return ("ADMIT", "OBSERVED_EQUAL") if value == expected else ("REFUSE", "OBSERVED_NOT_EQUAL")
    if p.get("check") == "NUMERIC_RANGE":
        lower, upper = p.get("minimum"), p.get("maximum")
        if (type(value) not in (int, float) or not isfinite(value) or
                type(lower) not in (int, float) or type(upper) not in (int, float) or
                not isfinite(lower) or not isfinite(upper) or lower > upper):
            return "INCONCLUSIVE", "INVALID_RANGE_OR_OBSERVATION"
        return ("ADMIT", "WITHIN_DECLARED_RANGE") if lower <= value <= upper else ("REFUSE", "OUTSIDE_DECLARED_RANGE")
    return "INCONCLUSIVE", "UNSUPPORTED_PROBE_CHECK"


def evaluate_semantics(ir: dict, observations: dict, as_of: str) -> dict:
    """Assess declared IR nodes using only caller-supplied, unauthenticated observations.

    Aggregate verdicts: REFUSE if any explicit deterministic contradiction;
    INCONCLUSIVE if any unsupported/missing node; ADMIT if *all nodes* are
    bounded checks satisfied. ADMIT is NOT proof of source authenticity.
    """
    if not isinstance(ir, dict) or ir.get("schema") != IR_SCHEMA:
        raise ValueError("Invalid typed IR schema")
    nodes = ir.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("Invalid IR node collection")
    if not isinstance(observations, dict):
        raise ValueError("Observations must be a mapping")
    if not isinstance(ir.get("source"), dict) or not isinstance(ir["source"].get("sha256"), str):
        raise ValueError("Missing IR source identity")
    expected_hash = _fingerprint({"source_sha256": ir["source"]["sha256"], "nodes": nodes})
    if expected_hash != ir.get("ir_sha256"):
        raise ValueError("IR fingerprint mismatch")
    observed_at = _instant(as_of)
    events = observations.get("events", {})
    probes = observations.get("probes", {})
    if not isinstance(events, dict) or not isinstance(probes, dict):
        raise ValueError("Events and probes must be mappings")
    findings = []
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("node_id"), str) or not isinstance(n.get("kind"), str):
            raise ValueError("Invalid typed node")
        if n.get("review", {}).get("approved") is not True or n.get("source", {}).get("source_sha256") != ir["source"]["sha256"]:
            raise ValueError("Unreviewed or source-mismatched IR node")
        kind = n["kind"]
        if kind == "TEMPORAL":
            verdict, reason = _temporal(n, events, observed_at)
        elif kind == "PROBE":
            verdict, reason = _probe(n, probes)
        else:
            verdict, reason = "INCONCLUSIVE", "RUNTIME_NOT_IMPLEMENTED"
        findings.append({"node_id": n["node_id"], "kind": kind, "verdict": verdict, "reason": reason})
    verdicts = {f["verdict"] for f in findings}
    overall = "REFUSE" if "REFUSE" in verdicts else "INCONCLUSIVE" if "INCONCLUSIVE" in verdicts else "ADMIT"
    return {
        "schema": RESULT_SCHEMA,
        "verdict": overall,
        "findings": findings,
        "ir_sha256": ir["ir_sha256"],
        "assurance": "DETERMINISTIC_CHECKS_ON_CALLER_SUPPLIED_UNAUTHENTICATED_OBSERVATIONS",
        "meaning": "ADMIT is bounded predicate satisfaction only, not semantic/source truth",
    }
