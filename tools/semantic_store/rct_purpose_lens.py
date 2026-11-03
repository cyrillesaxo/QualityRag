"""Purpose-scoped RCT lens contraction over a validated typed operator candidate.

This is an *experimental contract*, NOT an authenticated PackSpec. It enforces
explicit local preservation tests but cannot authorize semantic omissions.
Original source and supported witnesses remain reconstructable by source ID.
"""
from __future__ import annotations

from rct_grammar import _validate, _ident
from rct_induction import _read_labels
from rct_operator_ast import _evaluate_relations, _score, _validate_ast
from rct_typed_grammar import GRAMMAR_SCHEMA, RULE_SCHEMA, _grammar, _signature
from store import digest

CONTRACT_SCHEMA = "rct.purpose-contract/v1.5"


def make_contract(source: dict, labels: list[dict], *, purpose: str,
                  required_predicates: list[str], allowed_omission_predicates: list[str],
                  query_family: str = "labeled_binary_relation") -> dict:
    facts = _validate(source)
    records = _read_labels(labels)
    if not _ident(purpose) or query_family != "labeled_binary_relation":
        raise ValueError("Unsupported purpose/query family")
    valid = {fact["predicate"] for fact in facts}
    if (not isinstance(required_predicates, list)
            or not required_predicates
            or not isinstance(allowed_omission_predicates, list)
            or any(not _ident(p) for p in required_predicates + allowed_omission_predicates)
            or len(set(required_predicates)) != len(required_predicates)
            or len(set(allowed_omission_predicates)) != len(allowed_omission_predicates)
            or set(required_predicates) & set(allowed_omission_predicates)
            or not set(required_predicates + allowed_omission_predicates) <= valid):
        raise ValueError("Invalid required/optional distinction contract")
    contract = {
        "schema": CONTRACT_SCHEMA,
        "purpose": purpose,
        "query_family": query_family,
        "source_sha256": digest(source),
        "labels_sha256": digest(records),
        "required_predicates": sorted(required_predicates),
        "allowed_omission_predicates": sorted(allowed_omission_predicates),
        "review": "NOT_AUTHENTICATED",
        "packspec_completeness": "UNKNOWN",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    contract["fingerprint"] = digest(contract)
    return contract


def compile_purpose_lens(source: dict, labels: list[dict], *,
                         grammar: dict, rule: dict, assessment: dict,
                         contract: dict, lens_id: str) -> dict:
    facts = _validate(source)
    records = _read_labels(labels)
    spec = _grammar(grammar, facts)
    if not _ident(lens_id) or not isinstance(contract, dict):
        raise ValueError("Invalid lens identity or contract")
    c = dict(contract)
    ch = c.pop("fingerprint", None)
    if (ch != digest(c) or c.get("schema") != CONTRACT_SCHEMA
            or c.get("source_sha256") != digest(source)
            or c.get("labels_sha256") != digest(records)
            or c.get("query_family") != "labeled_binary_relation"
            or not _ident(c.get("purpose"))
            or c.get("review") != "NOT_AUTHENTICATED"
            or c.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Untrusted/mismatched purpose contract")
    required, optional = c.get("required_predicates"), c.get("allowed_omission_predicates")
    declared = {f["predicate"] for f in facts}
    if (not isinstance(required, list) or not required
            or not isinstance(optional, list)
            or len(required) != len(set(required))
            or len(optional) != len(set(optional))
            or set(required) & set(optional)
            or not set(required + optional) <= declared):
        raise ValueError("Invalid omission policy")

    r = dict(rule) if isinstance(rule, dict) else {}
    rh = r.pop("fingerprint", None)
    a = dict(assessment) if isinstance(assessment, dict) else {}
    ah = a.pop("fingerprint", None)
    if (rh != digest(r) or r.get("schema") != RULE_SCHEMA
            or r.get("status") != "CANDIDATE"
            or r.get("grammar_sha256") != digest(spec)
            or r.get("qualityrag_admission") != "INCONCLUSIVE"
            or ah != digest(a) or a.get("rule_sha256") != rh
            or a.get("grammar_sha256") != digest(spec)
            or a.get("heldout_source_sha256") != digest(source)
            or a.get("heldout_labels_sha256") != digest(records)
            or a.get("qualityrag_admission") != "INCONCLUSIVE"
            or a.get("finite_graph_verdict") != "SAT"):
        raise ValueError("No intact SAT structural candidate for given source/labels")
    _validate_ast(rule["ast"])
    if list(_signature(rule["ast"], spec["predicate_types"])) != rule.get("result_type"):
        raise ValueError("Invalid result type")
    if not set(required) <= {f["predicate"] for f in facts}:
        raise ValueError("Missing required distinctions")

    # Semantic obligations cannot be inferred from a structure alone.
    # Only locally verify that all explicitly supplied labels remain invariant.
    witness_ids = {fid for row in assessment["witnesses"]
                   for fid in row.get("fact_witness", [])}
    fact_ids = {f["id"] for f in facts}
    if not witness_ids <= fact_ids:
        raise ValueError("Witness refers to a missing source fact")
    protected = sorted(witness_ids | {
        f["id"] for f in facts if f["predicate"] in required
    })
    protected_set = set(protected)
    omitted = sorted(f["id"] for f in facts
                     if f["predicate"] in optional and f["id"] not in protected_set)
    kept = [f for f in facts if f["id"] not in set(omitted)]
    work = [0]
    full = _score(_evaluate_relations(facts, rule["ast"], work), records)
    narrowed = _score(_evaluate_relations(kept, rule["ast"], work), records)
    if ([row["prediction"] for row in full] !=
            [row["prediction"] for row in narrowed]
            or not all(row["match"] for row in narrowed)
            or a["finite_graph_verdict"] != "SAT"):
        raise ValueError("Projected lens breaks protected labeled answers")

    # The original source is referenced, not deleted; omissions are lens-scoped.
    by_id = {f["id"]: f for f in facts}
    lens = {
        "schema": "rct.source-lens/v0.6",
        "lens_id": lens_id, "purpose": c["purpose"],
        "source_sha256": digest(source),
        "required": list(required), "permitted_omissions": list(optional),
        "purpose_contract": contract,
        "source_fact_count": len(facts),
        "selected_fact_count": len(kept),
        "selected_fact_ids": sorted(f["id"] for f in kept),
        "omitted_fact_ids": omitted,
        "protected_fact_ids": protected,
        "candidate_claims": [{
            "fact_id": fid, "predicate": by_id[fid]["predicate"],
            "source_ref": by_id[fid]["source_ref"],
            "fact_sha256": digest(by_id[fid]),
            "status": "UNVERIFIED_SOURCE_CLAIM"}
            for fid in protected],
        "candidate_grammar": rule,
        "evaluation": assessment,
        "local_preservation": {
            "status": "DECLARED_LABELED_ANSWERS_PRESERVED",
            "label_count": len(records),
            "evaluation_work_units": work[0],
            "scope": "SUPPLIED_FINITE_GRAPH_AND_LABELS_ONLY",
        },
        "unresolved": ["source_authenticity", "packspec_completeness",
                       "external_semantic_adequacy"],
        "local_coverage": "STRUCTURAL_PROJECTION_ONLY",
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "packspec_completeness": "UNKNOWN",
        "grammar": "PURPOSE_GOVERNED_TYPED_LENS_CANDIDATE",
        "limitations": [
            "Purpose contract is caller-authored, not authenticated PackSpec",
            "Preservation is tested only for explicitly labeled structural pairs",
            "Omitted facts remain in original source; no global sufficiency proof",
            "No FF-RCT reconstruction or verified meaning-conservation claim",
        ],
    }
    lens["fingerprint"] = digest(lens)
    return lens
