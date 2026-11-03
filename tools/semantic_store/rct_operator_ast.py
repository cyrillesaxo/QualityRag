"""RCT v1.3 experimental typed operator AST: EDGE, PATH and AND.

Finite relational graph semantics only. Predicate labels and a bounded grammar
search are learned from authored training facts/labels. No domain-level proof,
source authentication, PackSpec admission or novel mathematical invention.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any

from rct_grammar import _validate, _ident
from rct_induction import _read_labels
from store import digest

SCHEMA = "rct.operator-ast/v1.3"
MAX_CANDIDATES = 400
MAX_WORK = 200000


def _validate_ast(ast: dict, depth: int = 0):
    if not isinstance(ast, dict) or depth > 5:
        raise ValueError("Invalid operator AST or depth")
    op = ast.get("op")
    if op == "EDGE":
        if set(ast) != {"op", "predicate"} or not _ident(ast["predicate"]):
            raise ValueError("Invalid EDGE")
        return
    if op not in ("PATH", "AND") or set(ast) != {"op", "left", "right"}:
        raise ValueError("Unsupported operator")
    _validate_ast(ast["left"], depth + 1)
    _validate_ast(ast["right"], depth + 1)


def _cost(ast):
    return 1 if ast["op"] == "EDGE" else 1 + _cost(ast["left"]) + _cost(ast["right"])


def _evaluate_relations(facts: list[dict], ast: dict, work: list[int]):
    """Returns (subject,object)->one deterministic fact-ID witness."""
    _validate_ast(ast)
    if ast["op"] == "EDGE":
        out = {}
        for edge in facts:
            work[0] += 1
            if work[0] > MAX_WORK:
                raise OverflowError("Graph evaluation budget")
            if edge["predicate"] == ast["predicate"]:
                pair = (edge["subject"], edge["object"])
                witness = [edge["id"]]
                if pair not in out or witness < out[pair]:
                    out[pair] = witness
        return out
    left = _evaluate_relations(facts, ast["left"], work)
    right = _evaluate_relations(facts, ast["right"], work)
    out = {}
    if ast["op"] == "PATH":
        idx = defaultdict(list)
        for (src, dst), witness in right.items():
            idx[src].append((dst, witness))
        for (src, mid), left_ids in left.items():
            for dst, right_ids in idx.get(mid, ()):
                work[0] += 1
                if work[0] > MAX_WORK:
                    raise OverflowError("Graph composition budget")
                pair = (src, dst)
                witness = left_ids + right_ids
                if pair not in out or witness < out[pair]:
                    out[pair] = witness
    else:
        for pair in left.keys() & right.keys():
            work[0] += 1
            if work[0] > MAX_WORK:
                raise OverflowError("Graph conjunction budget")
            out[pair] = sorted(set(left[pair] + right[pair]))
    return out


def _score(relations, labels):
    witnesses = []
    for x in labels:
        pair = (x["subject"], x["object"])
        hit = pair in relations
        witnesses.append({
            "subject": x["subject"], "object": x["object"],
            "label": "POSITIVE" if x["positive"] else "NEGATIVE",
            "prediction": "PRESENT" if hit else "ABSENT_IN_SUPPLIED_GRAPH",
            "match": hit == x["positive"],
            "fact_witness": relations.get(pair, []),
            "label_source_ref": x["source_ref"],
        })
    return witnesses


def _enumerate(predicates: list[str]):
    """Two levels of compositional exploration, unique ASTs only.

    Permits PATH(EDGE,EDGE), AND(EDGE,EDGE) and
    AND(PATH(EDGE,EDGE),EDGE). AND is canonicalized by string key.
    """
    edge = [dict(op="EDGE", predicate=p) for p in predicates]
    paths = [dict(op="PATH", left=a, right=b) for a in edge for b in edge]
    branch = [dict(op="AND", left=a, right=b) for a, b in combinations(edge, 2)]
    hybrid = []
    for path in paths:
        for guard in edge:
            hybrid.append(dict(op="AND", left=path, right=guard))
    return edge + paths + branch + hybrid


def induce_operator_ast(source: dict, examples: list[dict], *,
                        max_candidates: int = MAX_CANDIDATES) -> dict:
    facts = _validate(source)
    labels = _read_labels(examples)
    if not any(x["positive"] for x in labels) or not any(
            not x["positive"] for x in labels):
        raise ValueError("Explicit positive and negative labels required")
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError("Invalid candidate budget")
    predicates = sorted({f["predicate"] for f in facts})
    expressions = _enumerate(predicates)
    result = {
        "schema": SCHEMA,
        "training_source_sha256": digest(source),
        "training_labels_sha256": digest(labels),
        "search_space": "EDGE_PATH_AND_PATH_AND_EDGE",
        "enumerated_candidates": len(expressions),
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "packspec_completeness": "UNKNOWN",
    }
    if len(expressions) > max_candidates:
        result.update(status="UNKNOWN", reason="CANDIDATE_BUDGET_EXCEEDED")
    else:
        valid = []
        work = [0]
        try:
            for ast in expressions:
                relations = _evaluate_relations(facts, ast, work)
                witnesses = _score(relations, labels)
                if all(x["match"] for x in witnesses):
                    valid.append((ast, witnesses))
            if not valid:
                result.update(status="UNKNOWN", reason="NO_CONSISTENT_OPERATOR")
            else:
                minimum = min(_cost(ast) for ast, _ in valid)
                best = [(ast, witnesses) for ast, witnesses in valid
                        if _cost(ast) == minimum]
                if len(best) != 1:
                    result.update(status="UNKNOWN", reason="AMBIGUOUS_MINIMAL_OPERATOR",
                                  minimal_candidate_count=len(best))
                else:
                    ast, witnesses = best[0]
                    result.update(status="CANDIDATE", ast=ast, ast_nodes=_cost(ast),
                                  training_witnesses=witnesses,
                                  structural_training_verdict="SAT")
        except OverflowError:
            result.update(status="UNKNOWN", reason="EVALUATION_BUDGET_EXCEEDED")
        result["evaluation_work_units"] = work[0]
    result["fingerprint"] = digest(result)
    return result


def validate_operator_ast(training: dict, rule: dict, heldout: dict,
                          examples: list[dict]) -> dict:
    _validate(training)
    facts = _validate(heldout)
    labels = _read_labels(examples)
    if digest(training) == digest(heldout):
        raise ValueError("Heldout graph must differ from training graph")
    body = dict(rule) if isinstance(rule, dict) else {}
    fingerprint = body.pop("fingerprint", None)
    if (fingerprint != digest(body) or body.get("schema") != SCHEMA
            or body.get("status") != "CANDIDATE"
            or body.get("training_source_sha256") != digest(training)
            or body.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Untrusted candidate AST")
    _validate_ast(rule.get("ast"))
    work = [0]
    try:
        evidence = _score(_evaluate_relations(facts, rule["ast"], work), labels)
        failures = [x for x in evidence if not x["match"]]
        state = "COUNTEREXAMPLE" if failures else "FINITE_GRAPH_MATCH"
        verdict = "UNSAT" if failures else "SAT"
    except OverflowError:
        evidence, failures, state, verdict = [], [], "UNKNOWN", "UNKNOWN"
    output = {
        "schema": "rct.operator-validation/v1.3",
        "rule_sha256": fingerprint,
        "heldout_source_sha256": digest(heldout),
        "heldout_labels_sha256": digest(labels),
        "status": state, "finite_graph_verdict": verdict,
        "witnesses": evidence, "counterexamples": failures,
        "evaluation_work_units": work[0],
        "qualityrag_admission": "INCONCLUSIVE",
        "boundary": "Labeled graph agreement, not domain truth or semantic admission",
    }
    output["fingerprint"] = digest(output)
    return output


def compile_operator_lens(source: dict, *, rule: dict, assessment: dict,
                          lens_id: str, purpose: str) -> dict:
    _validate(source)
    if not _ident(lens_id) or not _ident(purpose):
        raise ValueError("Invalid lens identity/purpose")
    r = dict(rule) if isinstance(rule, dict) else {}
    rf = r.pop("fingerprint", None)
    a = dict(assessment) if isinstance(assessment, dict) else {}
    af = a.pop("fingerprint", None)
    if (rf != digest(r) or r.get("schema") != SCHEMA
            or r.get("status") != "CANDIDATE"
            or r.get("qualityrag_admission") != "INCONCLUSIVE"
            or af != digest(a)
            or a.get("rule_sha256") != rf
            or a.get("heldout_source_sha256") != digest(source)
            or a.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Mutated rule, evaluation or source")
    lens = {
        "schema": "rct.source-lens/v0.6",
        "lens_id": lens_id, "purpose": purpose,
        "source_sha256": digest(source),
        "required": ["labeled_typed_operator_scope"], "permitted_omissions": [],
        "candidate_claims": [
            {"subject": x["subject"], "object": x["object"],
             "fact_witness": x["fact_witness"], "label_source_ref": x["label_source_ref"],
             "status": "UNVERIFIED_SOURCE_CLAIM"}
            for x in assessment["witnesses"]],
        "candidate_grammar": rule, "evaluation": assessment,
        "unresolved": [] if assessment["finite_graph_verdict"] == "SAT"
                      else ["operator_validation_not_satisfied"],
        "local_coverage": ("LABELED_FINITE_GRAPH_CHECKED"
                           if assessment["finite_graph_verdict"] == "SAT" else "UNKNOWN"),
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "packspec_completeness": "UNKNOWN",
        "grammar": "BOUNDED_TYPED_OPERATOR_AST",
        "limitations": [
            "Operator family authored in advance, not invented from first principles",
            "Negative labels not authenticated and unlabeled pairs remain unknown",
            "No FF-RCT reconstruction, PackSpec proof or semantic admission",
        ],
    }
    lens["fingerprint"] = digest(lens)
    return lens
