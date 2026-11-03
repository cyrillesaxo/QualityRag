"""Exhaustive finite-relation conservation for a purpose-scoped RCT candidate.

Tests ALL reachable subject/object pairs of the declared operator AST, not
merely training labels. This is a bounded structural theorem on one supplied
graph, not semantic completeness or source authority.
"""
from __future__ import annotations

from rct_grammar import _validate
from rct_operator_ast import _evaluate_relations, _validate_ast
from store import digest

SCHEMA = "rct.finite-relation-conservation/v2"
MAX_FACTS = 10000


def audit_finite_conservation(source: dict, lens: dict,
                              *, max_work_units: int = 200000) -> dict:
    facts = _validate(source)
    if (type(max_work_units) is not int or not 1 <= max_work_units <= 200000):
        raise ValueError("Invalid finite-evaluation work limit")
    if not isinstance(lens, dict):
        raise ValueError("Purpose lens required")
    l = dict(lens)
    fingerprint = l.pop("fingerprint", None)
    if (fingerprint != digest(l) or l.get("schema") != "rct.source-lens/v0.6"
            or l.get("source_sha256") != digest(source)
            or l.get("qualityrag_admission") != "INCONCLUSIVE"
            or l.get("grammar") != "PURPOSE_GOVERNED_TYPED_LENS_CANDIDATE"):
        raise ValueError("Untrusted or stale purpose-specific lens")
    rule = lens.get("candidate_grammar")
    if not isinstance(rule, dict):
        raise ValueError("Missing grammar candidate")
    r = dict(rule)
    rule_fingerprint = r.pop("fingerprint", None)
    if (rule_fingerprint != digest(r) or rule.get("status") != "CANDIDATE"
            or rule.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Unverified or modified rule")
    ast = rule.get("ast")
    _validate_ast(ast)
    required = lens.get("required")
    optional = lens.get("permitted_omissions")
    selected = lens.get("selected_fact_ids")
    omitted = lens.get("omitted_fact_ids")
    protected = lens.get("protected_fact_ids")
    if (not all(isinstance(x, list) for x in
                (required, optional, selected, omitted, protected))
            or not required
            or any(len(x) != len(set(x)) for x in
                   (required, optional, selected, omitted, protected))
            or set(required) & set(optional)):
        raise ValueError("Missing or contradictory preservation declarations")
    by_id = {f["id"]: f for f in facts}
    original = set(by_id)
    if (set(selected) | set(omitted) != original
            or set(selected) & set(omitted)
            or not set(protected) <= set(selected)
            or any(by_id[fid]["predicate"] not in optional for fid in omitted)
            or any(fid not in selected for fid, f in by_id.items()
                   if f["predicate"] in required)):
        raise ValueError("Lens omitted an unsupported or protected source fact")
    kept = [f for f in facts if f["id"] in set(selected)]
    work = [0]
    try:
        full = _evaluate_relations(facts, ast, work)
        if work[0] > max_work_units:
            raise OverflowError()
        projected = _evaluate_relations(kept, ast, work)
        if work[0] > max_work_units:
            raise OverflowError()
    except OverflowError:
        status, verdict = "UNKNOWN", "INCONCLUSIVE"
        lost, gained = [], []
        full_count = projected_count = None
    else:
        lost = sorted([list(pair) for pair in full.keys() - projected.keys()])
        gained = sorted([list(pair) for pair in projected.keys() - full.keys()])
        status = "EXACT_FINITE_RELATION_MATCH" if not (lost or gained) else "COUNTEREXAMPLE"
        verdict = "SAT" if status == "EXACT_FINITE_RELATION_MATCH" else "UNSAT"
        full_count, projected_count = len(full), len(projected)
    receipt = {
        "schema": SCHEMA,
        "lens_fingerprint": fingerprint,
        "source_sha256": digest(source),
        "operator_rule_sha256": rule_fingerprint,
        "status": status,
        "finite_structural_verdict": verdict,
        "lost_pairs": lost,
        "gained_pairs": gained,
        "full_relation_size": full_count,
        "projected_relation_size": projected_count,
        "checked_work_units": work[0],
        "scope": "ALL_PAIRS_IN_ONE_DECLARED_FINITE_GRAPH_AND_OPERATOR_ONLY",
        "semantic_completeness": "UNKNOWN",
        "source_truth": "UNVERIFIED",
        "omission_authority": "NOT_ESTABLISHED",
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt
