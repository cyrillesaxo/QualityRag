"""Bounded supervised AST rule induction with positive and negative witnesses.

Research only. Finds relation-path grammars of length 1-4 from labeled examples,
not novel mathematical primitives. Finite graph checks are NOT semantic truth.
Unlabeled pairs are UNKNOWN; never interpret missing edges as negative evidence.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from rct_grammar import _validate, _ident
from store import digest

SCHEMA = "rct.induced-rule/v1.1"
MAX_LABELED = 200
MAX_WORK = 100_000


def _read_labels(examples: list[dict], *, max_examples: int = MAX_LABELED):
    if not isinstance(examples, list) or not 1 <= len(examples) <= max_examples:
        raise ValueError("Expected bounded labeled examples")
    seen = set()
    records = []
    for row in examples:
        if not isinstance(row, dict) or not all(_ident(row.get(k)) for k in
                 ("subject", "object", "source_ref")):
            raise ValueError("Each example requires subject, object, source_ref")
        if type(row.get("positive")) is not bool:
            raise ValueError("Labels must explicitly declare positive boolean")
        key = (row["subject"], row["object"])
        if key in seen:
            raise ValueError("Duplicate or contradictory label")
        seen.add(key)
        records.append(dict(row))
    return records


def _edge_index(facts: list[dict]):
    index = defaultdict(list)
    for f in facts:
        index[f["subject"]].append(f)
    return {k: sorted(v, key=lambda e: e["id"]) for k, v in index.items()}


def _paths(index: dict, start: str, end: str, max_depth: int,
           budget: list[int]) -> dict[tuple[str, ...], list[str]]:
    """Return shortest cited witness for each discovered predicate sequence.

    Revisiting nodes is allowed, but traversal depth and expansion count bounded.
    A zero-length path never establishes a positive relationship.
    """
    out = {}
    stack = [(start, (), ())]
    while stack:
        node, predicates, fact_ids = stack.pop()
        if len(predicates) and node == end:
            old = out.get(predicates)
            if old is None or list(fact_ids) < old:
                out[predicates] = list(fact_ids)
        if len(predicates) == max_depth:
            continue
        for edge in index.get(node, []):
            budget[0] += 1
            if budget[0] > MAX_WORK:
                raise OverflowError("Path enumeration budget exceeded")
            stack.append((edge["object"],
                          predicates + (edge["predicate"],),
                          fact_ids + (edge["id"],)))
    return out


def _evaluate(facts: list[dict], labels: list[dict],
              sequence: tuple[str, ...], budget: list[int]):
    """Independent evaluator for the selected relation-path expression."""
    index = _edge_index(facts)
    answers = []
    for example in labels:
        frontier = {example["subject"]: []}
        for predicate in sequence:
            next_frontier = {}
            for node, witness in sorted(frontier.items()):
                for edge in index.get(node, []):
                    budget[0] += 1
                    if budget[0] > MAX_WORK:
                        raise OverflowError("Rule verification budget exceeded")
                    if edge["predicate"] == predicate:
                        ids = witness + [edge["id"]]
                        old = next_frontier.get(edge["object"])
                        if old is None or ids < old:
                            next_frontier[edge["object"]] = ids
            frontier = next_frontier
        matched = example["object"] in frontier
        answers.append({
            "subject": example["subject"], "object": example["object"],
            "label": "POSITIVE" if example["positive"] else "NEGATIVE",
            "prediction": "PRESENT" if matched else "ABSENT_IN_SUPPLIED_GRAPH",
            "match": matched == example["positive"],
            "fact_witness": frontier.get(example["object"], []),
            "label_source_ref": example["source_ref"],
        })
    return answers


def induce_rule(source: dict, examples: list[dict], *,
                max_depth: int = 3) -> dict[str, Any]:
    """Select unique shortest candidate consistent with explicit labels.

    No absence-as-falsity inference outside labeled examples. Ambiguous, missing,
    or unbounded searches produce UNKNOWN instead of silently picking a rule.
    """
    facts = _validate(source)
    labels = _read_labels(examples)
    if type(max_depth) is not int or not 1 <= max_depth <= 4:
        raise ValueError("max_depth must be 1..4")
    if not any(row["positive"] for row in labels) or not any(
            not row["positive"] for row in labels):
        raise ValueError("Positive and negative witnesses are both required")
    result = {
        "schema": SCHEMA, "training_source_sha256": digest(source),
        "training_labels_sha256": digest(labels),
        "max_depth": max_depth,
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "domain_semantics": "UNKNOWN",
    }
    budget = [0]
    try:
        idx = _edge_index(facts)
        positives = [row for row in labels if row["positive"]]
        common = None
        witnesses = {}
        for row in positives:
            discovered = _paths(idx, row["subject"], row["object"],
                                max_depth, budget)
            common = set(discovered) if common is None else common & set(discovered)
            witnesses[(row["subject"], row["object"])] = discovered
        candidates = []
        for sequence in sorted(common or [], key=lambda s: (len(s), s)):
            answers = _evaluate(facts, labels, sequence, budget)
            if all(row["match"] for row in answers):
                candidates.append((sequence, answers))
        if not candidates:
            result.update({"status": "UNKNOWN", "reason": "NO_RULE_SATISFIES_ALL_LABELS",
                           "candidate_count": 0})
        else:
            best_length = len(candidates[0][0])
            best = [(s, a) for s, a in candidates if len(s) == best_length]
            if len(best) != 1:
                result.update({"status": "UNKNOWN", "reason": "AMBIGUOUS_MINIMAL_GRAMMAR",
                               "candidate_count": len(candidates),
                               "minimal_candidate_count": len(best)})
            else:
                seq, answers = best[0]
                result.update({
                    "status": "CANDIDATE",
                    "operator": "COMPOSE_VARIABLE_LENGTH_PATH",
                    "predicate_sequence": list(seq),
                    "candidate_count": len(candidates),
                    "minimum_depth": len(seq),
                    "training_witnesses": answers,
                    "structural_training_verdict": "SAT",
                    "not_proven": ["unlabeled pairs", "source authenticity",
                                    "domain semantics", "PackSpec completeness"],
                })
    except OverflowError:
        result.update({"status": "UNKNOWN", "reason": "SEARCH_BUDGET_EXCEEDED"})
    result["search_work_units"] = budget[0]
    result["fingerprint"] = digest(result)
    return result


def validate_rule(training_source: dict, rule: dict,
                  heldout_source: dict, heldout_examples: list[dict]) -> dict:
    """Check an induced candidate against independent labeled graph examples.

    Positive and explicitly labeled negative pairs are checked in heldout data.
    Passing is evidence for finite graph behavior, never semantic admission.
    """
    _validate(training_source)
    facts = _validate(heldout_source)
    labels = _read_labels(heldout_examples)
    if digest(training_source) == digest(heldout_source):
        raise ValueError("Heldout source must differ from training source")
    if digest(training_source) != rule.get("training_source_sha256"):
        raise ValueError("Training source fingerprint mismatch")
    clean = dict(rule)
    fingerprint = clean.pop("fingerprint", None)
    if (fingerprint != digest(clean) or rule.get("schema") != SCHEMA
            or rule.get("status") != "CANDIDATE"
            or rule.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Rule is not an intact candidate")
    sequence = rule.get("predicate_sequence")
    if not (isinstance(sequence, list) and 1 <= len(sequence) <= 4
            and all(_ident(x) for x in sequence)):
        raise ValueError("Invalid rule sequence")
    budget = [0]
    try:
        evidence = _evaluate(facts, labels, tuple(sequence), budget)
        failures = [row for row in evidence if not row["match"]]
        verdict = "UNSAT" if failures else "SAT"
        status = "COUNTEREXAMPLE" if failures else "FINITE_GRAPH_MATCH"
    except OverflowError:
        evidence, failures, status, verdict = [], [], "UNKNOWN", "UNKNOWN"
    result = {
        "schema": "rct.induced-rule-validation/v1.1",
        "rule_sha256": rule["fingerprint"],
        "heldout_source_sha256": digest(heldout_source),
        "heldout_labels_sha256": digest(labels),
        "status": status,
        "finite_graph_verdict": verdict,
        "witnesses": evidence,
        "counterexamples": failures,
        "evaluation_work_units": budget[0],
        "qualityrag_admission": "INCONCLUSIVE",
        "limitations": [
            "Only labeled pairs have positive/negative supervision",
            "Heldout source claims are unauthenticated",
            "Finite graph consistency does not establish general semantic validity",
            "Operator combinator is predefined, sequence learned from examples",
        ],
    }
    result["fingerprint"] = digest(result)
    return result


def compile_induced_lens(source: dict, *, rule: dict, assessment: dict,
                         lens_id: str, purpose: str) -> dict:
    """Persist candidate through the existing rct_lens adapter, never ADMIT."""
    _validate(source)
    if not _ident(lens_id) or not _ident(purpose):
        raise ValueError("Missing lens identity/purpose")
    candidate = dict(rule) if isinstance(rule, dict) else {}
    rule_fingerprint = candidate.pop("fingerprint", None)
    if (rule_fingerprint != digest(candidate)
            or candidate.get("schema") != SCHEMA
            or candidate.get("status") != "CANDIDATE"
            or candidate.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Rule fingerprint or candidate posture mismatch")
    a = dict(assessment) if isinstance(assessment, dict) else {}
    ah = a.pop("fingerprint", None)
    if (ah != digest(a) or assessment.get("rule_sha256") != rule_fingerprint
            or assessment.get("heldout_source_sha256") != digest(source)
            or assessment.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Assessment fingerprint or source mismatch")
    result = {
        "schema": "rct.source-lens/v0.6",
        "lens_id": lens_id, "purpose": purpose,
        "source_sha256": digest(source),
        "required": ["explicit_labeled_structural_pairs"],
        "permitted_omissions": [],
        "candidate_claims": [
            {"subject": row["subject"], "object": row["object"],
             "fact_witness": row["fact_witness"],
             "label_source_ref": row["label_source_ref"],
             "status": "UNVERIFIED_SOURCE_CLAIM"}
            for row in assessment["witnesses"]
        ],
        "candidate_grammar": rule,
        "evaluation": assessment,
        "unresolved": ([] if assessment.get("finite_graph_verdict") == "SAT"
                       else ["failed_or_unknown_validation"]),
        "local_coverage": ("LABELED_FINITE_GRAPH_CHECKED"
                           if assessment.get("finite_graph_verdict") == "SAT" else "UNKNOWN"),
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "packspec_completeness": "UNKNOWN",
        "grammar": "BOUNDED_LABELED_PATH_SYNTHESIS",
        "limitations": [
            "No semantic or global completeness admission",
            "Labeled negative pairs are source claims, not closed-world truth",
            "Only tested for one bounded relation-path operator family",
        ],
    }
    result["fingerprint"] = digest(result)
    return result
