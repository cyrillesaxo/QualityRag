"""RCT v1.2: supervised induction of a *branching* two-predicate conjunction.

Operator family is bounded (parallel-edge AND). The predicate pair is learned.
This is not autonomous mathematical invention. Labels are externally supplied,
source refs unauthenticated, and semantic admission always INCONCLUSIVE.

Positive examples require TWO independent typed facts relating the same
(subject, object). Negative examples are explicitly labeled counterwitnesses.
Unlabeled pairs remain UNKNOWN.
"""
from __future__ import annotations
from collections import defaultdict
from itertools import combinations
from typing import Any

from rct_grammar import _validate, _ident
from rct_induction import _read_labels
from store import digest

SCHEMA = "rct.branch-rule/v1.2"
MAX_CANDIDATES = 256


def _by_pair(facts: list[dict]) -> dict[tuple[str, str], dict[str, list[str]]]:
    pairs = defaultdict(lambda: defaultdict(list))
    for f in facts:
        pairs[(f["subject"], f["object"])][f["predicate"]].append(f["id"])
    return {key: {pred: sorted(ids) for pred, ids in variants.items()}
            for key, variants in pairs.items()}


def _predict(pair_index: dict, examples: list[dict], predicates: tuple[str, str]) -> list[dict]:
    output = []
    for example in examples:
        edges = pair_index.get((example["subject"], example["object"]), {})
        hits = [edges.get(p, []) for p in predicates]
        present = all(hits)
        support = [hits[0][0], hits[1][0]] if present else []
        output.append({
            "subject": example["subject"], "object": example["object"],
            "label": "POSITIVE" if example["positive"] else "NEGATIVE",
            "prediction": "PRESENT" if present else "ABSENT_IN_SUPPLIED_GRAPH",
            "match": present == example["positive"],
            "fact_witness": support,
            "label_source_ref": example["source_ref"],
        })
    return output


def induce_branch_rule(source: dict, examples: list[dict],
                       *, max_candidates: int = MAX_CANDIDATES) -> dict[str, Any]:
    facts = _validate(source)
    labels = _read_labels(examples)
    if not any(x["positive"] for x in labels) or not any(
            not x["positive"] for x in labels):
        raise ValueError("Positive and negative witnesses both required")
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError("Invalid candidate bound")

    pair_index = _by_pair(facts)
    positive = [x for x in labels if x["positive"]]
    common = None
    for example in positive:
        predicates = set(pair_index.get((example["subject"], example["object"]), {}))
        common = predicates if common is None else common & predicates
    names = sorted(common or [])
    count = len(names) * (len(names) - 1) // 2
    result = {
        "schema": SCHEMA,
        "operator": "CONJUNCT_PARALLEL_EDGES",
        "training_source_sha256": digest(source),
        "training_labels_sha256": digest(labels),
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "domain_semantics": "UNKNOWN",
        "search_candidate_count": count,
    }
    if count > max_candidates:
        result.update({"status": "UNKNOWN", "reason": "SEARCH_BUDGET_EXCEEDED"})
    else:
        valid = []
        for pair in combinations(names, 2):
            answers = _predict(pair_index, labels, pair)
            if all(x["match"] for x in answers):
                valid.append((pair, answers))
        if len(valid) != 1:
            result.update({
                "status": "UNKNOWN",
                "reason": ("NO_CONSISTENT_BRANCH_RULE" if not valid
                           else "AMBIGUOUS_BRANCH_RULE"),
                "consistent_candidate_count": len(valid),
            })
        else:
            predicates, answers = valid[0]
            result.update({
                "status": "CANDIDATE",
                "predicate_pair": list(predicates),
                "training_witnesses": answers,
                "structural_training_verdict": "SAT",
                "consistent_candidate_count": 1,
                "not_proven": [
                    "unlabeled pairs", "source truth", "PackSpec completeness",
                    "necessity of conjunction outside the supplied labels",
                ],
            })
    result["fingerprint"] = digest(result)
    return result


def validate_branch_rule(training: dict, rule: dict, heldout: dict,
                         examples: list[dict]) -> dict[str, Any]:
    _validate(training)
    facts = _validate(heldout)
    labels = _read_labels(examples)
    if digest(training) == digest(heldout):
        raise ValueError("Heldout source must differ from training")
    if not isinstance(rule, dict):
        raise ValueError("Invalid rule")
    body = dict(rule)
    fingerprint = body.pop("fingerprint", None)
    pair = body.get("predicate_pair")
    if (fingerprint != digest(body) or body.get("schema") != SCHEMA
            or body.get("status") != "CANDIDATE"
            or body.get("operator") != "CONJUNCT_PARALLEL_EDGES"
            or body.get("training_source_sha256") != digest(training)
            or body.get("qualityrag_admission") != "INCONCLUSIVE"
            or not isinstance(pair, list) or len(pair) != 2
            or not all(_ident(p) for p in pair) or pair != sorted(set(pair))):
        raise ValueError("Untrusted or invalid branching grammar")
    witnesses = _predict(_by_pair(facts), labels, (pair[0], pair[1]))
    failures = [x for x in witnesses if not x["match"]]
    result = {
        "schema": "rct.branch-rule-validation/v1.2",
        "rule_sha256": fingerprint,
        "heldout_source_sha256": digest(heldout),
        "heldout_labels_sha256": digest(labels),
        "status": "COUNTEREXAMPLE" if failures else "FINITE_GRAPH_MATCH",
        "finite_graph_verdict": "UNSAT" if failures else "SAT",
        "witnesses": witnesses,
        "counterexamples": failures,
        "qualityrag_admission": "INCONCLUSIVE",
        "limitation": "Agreement for explicitly labeled pairs, not universal semantic equivalence",
    }
    result["fingerprint"] = digest(result)
    return result


def compile_branch_lens(heldout: dict, *, rule: dict, assessment: dict,
                        lens_id: str, purpose: str) -> dict:
    """Produce a non-admitted artifact for existing rct_lens.persist_lens."""
    _validate(heldout)
    if not _ident(lens_id) or not _ident(purpose):
        raise ValueError("Lens identity/purpose required")
    if not isinstance(rule, dict) or not isinstance(assessment, dict):
        raise ValueError("Missing rule or assessment")
    r = dict(rule)
    rf = r.pop("fingerprint", None)
    a = dict(assessment)
    af = a.pop("fingerprint", None)
    if (rf != digest(r) or r.get("schema") != SCHEMA
            or r.get("status") != "CANDIDATE"
            or r.get("qualityrag_admission") != "INCONCLUSIVE"
            or af != digest(a)
            or a.get("rule_sha256") != rf
            or a.get("heldout_source_sha256") != digest(heldout)
            or a.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Rule or evaluation receipt has been modified")
    lens = {
        "schema": "rct.source-lens/v0.6",
        "lens_id": lens_id, "purpose": purpose,
        "source_sha256": digest(heldout),
        "required": ["explicitly_labeled_parallel_conjunction"],
        "permitted_omissions": [],
        "candidate_claims": [
            {"subject": x["subject"], "object": x["object"],
             "label": x["label"], "support_fact_ids": x["fact_witness"],
             "label_source_ref": x["label_source_ref"],
             "status": "UNVERIFIED_SOURCE_CLAIM"}
            for x in assessment["witnesses"]
        ],
        "candidate_grammar": rule, "evaluation": assessment,
        "unresolved": ([] if assessment["finite_graph_verdict"] == "SAT"
                       else ["counterexample_or_unknown"]),
        "local_coverage": ("LABELED_FINITE_GRAPH_CHECKED"
                           if assessment["finite_graph_verdict"] == "SAT" else "UNKNOWN"),
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "packspec_completeness": "UNKNOWN",
        "grammar": "BOUNDED_PARALLEL_CONJUNCTION_INDUCTION",
        "limitations": [
            "Parallel conjunction family predefined; learned predicates only",
            "No semantic validity outside labeled finite graph",
            "Labels and source claims unauthenticated",
        ],
    }
    lens["fingerprint"] = digest(lens)
    return lens
