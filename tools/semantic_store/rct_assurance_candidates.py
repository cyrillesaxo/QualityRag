"""Bounded APX-inspired diagnostic candidates: witness cover, repair, drift.

Not a port of canonical private WBC/HCR/RCOC algorithms. The repository
currently exposes native APX receipts, not the corresponding full engines.
This module records deterministic structural checks and refuses to certify
semantic authority.
"""
from __future__ import annotations

from rct_grammar import _validate
from store import digest

SCHEMA = "rct.assurance-candidates/v2"


def witness_cover_candidate(lens: dict, *, max_witnesses: int = 200) -> dict:
    """Greedy finite fact-cover for supplied structural positive witnesses.

    Not guaranteed minimum cardinality; no semantic entailment is implied.
    """
    assessment = lens.get("evaluation") if isinstance(lens, dict) else None
    if not isinstance(assessment, dict) or not isinstance(assessment.get("witnesses"), list):
        raise ValueError("Missing finite witness assessment")
    positive = [x for x in assessment["witnesses"]
                if x.get("label") == "POSITIVE" and x.get("match") is True]
    if not positive or len(positive) > max_witnesses:
        raise ValueError("Missing/budget-exceeding positive witnesses")
    by_id = {}
    for idx, row in enumerate(positive):
        ids = row.get("fact_witness")
        if not isinstance(ids, list) or not ids:
            raise ValueError("Positive fact proof missing")
        for fact_id in ids:
            by_id.setdefault(fact_id, set()).add(idx)
    uncovered = set(range(len(positive)))
    chosen = []
    while uncovered:
        fid, hits = min(
            ((fid, coverage & uncovered) for fid, coverage in by_id.items()),
            key=lambda pair: (-len(pair[1]), pair[0]))
        if not hits:
            raise ValueError("Witness coverage gap")
        chosen.append(fid)
        uncovered.difference_update(hits)
    result = {
        "schema": SCHEMA, "kind": "GREEDY_WITNESS_FACT_COVER",
        "lens_fingerprint": lens.get("fingerprint"),
        "covered_labeled_positives": len(positive),
        "selected_fact_ids": sorted(by_id),
        "representative_fact_ids": sorted(chosen),
        "proof_preservation": "ALL_FACTS_FROM_SUPPLIED_POSITIVE_WITNESSES",
        "minimality": "NOT_PROVEN",
        "semantic_support": "UNKNOWN",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    result["fingerprint"] = digest(result)
    return result


def bounded_repair_candidates(governance_receipt: dict, *,
                              max_actions: int = 32) -> dict:
    """Prioritize existing Wgap and blocker descriptions without claiming HCR."""
    if type(max_actions) is not int or not 1 <= max_actions <= 32:
        raise ValueError("Invalid repair budget")
    gaps = governance_receipt.get("witness_coverage", {}).get("wgap", [])
    blockers = governance_receipt.get("blockers", [])
    if not isinstance(gaps, list) or not isinstance(blockers, list):
        raise ValueError("Missing governance diagnostics")
    actions = []
    for gap in sorted(gaps, key=lambda g: g["requirement_id"]):
        if gap.get("missing_sources", 0):
            actions.append({
                "kind": "REQUEST_INDEPENDENT_EVIDENCE_REVIEW",
                "requirement_id": gap["requirement_id"],
                "minimum_additional_declared_sources": gap["missing_sources"],
                "reason": "DECLARED_ORIGIN_EVIDENCE_GAP",
            })
    for blocker in sorted(set(blockers)):
        if blocker in ("OMISSION_SAFETY_NOT_ESTABLISHED",
                       "OMISSION_AUTHORIZATION_NOT_ESTABLISHED",
                       "RCT_OMISSION_MEANING_NOT_VERIFIED"):
            actions.append({"kind": "REQUEST_SEMANTIC_OMISSION_REVIEW",
                            "reason": blocker})
    limited = actions[:max_actions]
    result = {
        "schema": SCHEMA, "kind": "BOUNDED_RECOVERY_CANDIDATES",
        "actions": limited, "truncated": len(actions) > max_actions,
        "automatic_execution": False,
        "semantic_recovery": "NOT_VERIFIED",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    result["fingerprint"] = digest(result)
    return result


def structural_drift_candidate(previous: dict, current: dict) -> dict:
    """Detect immutable source-revision differences; do not claim RCOC parity."""
    old = {f["id"]: f for f in _validate(previous)}
    new = {f["id"]: f for f in _validate(current)}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(fid for fid in old.keys() & new.keys()
                     if digest(old[fid]) != digest(new[fid]))
    result = {
        "schema": SCHEMA, "kind": "STRUCTURAL_SOURCE_DRIFT",
        "previous_source_sha256": digest(previous),
        "current_source_sha256": digest(current),
        "added_fact_ids": added, "removed_fact_ids": removed,
        "changed_fact_ids": changed,
        "requires_revalidation": bool(added or removed or changed),
        "semantic_drift": "UNKNOWN",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    result["fingerprint"] = digest(result)
    return result
