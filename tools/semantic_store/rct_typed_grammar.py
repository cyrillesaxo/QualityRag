"""RCT v1.4 declarative typed grammar search over finite relations.

Operator syntax is explicit input; no code execution or semantic authorization.
Predicates have declared source/target types. Search produces typed AST candidates
and selects a unique minimum-cost expression fitting labeled examples.
"""
from __future__ import annotations
from collections import defaultdict
from itertools import product
from typing import Any

from rct_grammar import _validate, _ident
from rct_induction import _read_labels
from rct_operator_ast import _evaluate_relations, _score, _validate_ast
from store import digest

GRAMMAR_SCHEMA = "rct.typed-operator-grammar/v1.4"
RULE_SCHEMA = "rct.typed-rule/v1.4"
ALLOWED = frozenset(("EDGE", "PATH", "AND"))


def _grammar(spec: dict, facts: list[dict]) -> dict:
    if not isinstance(spec, dict) or spec.get("schema") != GRAMMAR_SCHEMA:
        raise ValueError("Typed grammar schema required")
    types = spec.get("predicate_types")
    if not isinstance(types, dict) or not types or len(types) > 16:
        raise ValueError("Bounded predicate types required")
    for name, endpoints in types.items():
        if not (_ident(name) and isinstance(endpoints, list)
                and len(endpoints) == 2 and all(_ident(x) for x in endpoints)):
            raise ValueError("Invalid predicate type signature")
    if any(f["predicate"] not in types for f in facts):
        raise ValueError("Undeclared source predicate")
    operators = spec.get("operators")
    if not isinstance(operators, list) or not operators or len(set(operators)) != len(operators):
        raise ValueError("Unique operators required")
    if set(operators) - ALLOWED or "EDGE" not in operators:
        raise ValueError("Unsupported operator set")
    max_nodes = spec.get("max_ast_nodes")
    max_candidates = spec.get("max_candidates")
    if (type(max_nodes) is not int or not 1 <= max_nodes <= 7
            or type(max_candidates) is not int or not 1 <= max_candidates <= 5000):
        raise ValueError("Invalid bounded search limits")
    return spec


def _signature(ast: dict, types: dict) -> tuple[str, str]:
    if ast["op"] == "EDGE":
        return tuple(types[ast["predicate"]])
    left = _signature(ast["left"], types)
    right = _signature(ast["right"], types)
    if ast["op"] == "AND":
        if left != right:
            raise ValueError("AND requires identical relation endpoint types")
        return left
    if left[1] != right[0]:
        raise ValueError("PATH endpoint type mismatch")
    return left[0], right[1]


def _canonical(ast: dict) -> str:
    return digest(ast)


def _enumerate(spec: dict) -> tuple[list[dict], int]:
    types = spec["predicate_types"]
    by_size: dict[int, list[dict]] = defaultdict(list)
    by_size[1] = [{"op": "EDGE", "predicate": p} for p in sorted(types)]
    max_nodes = spec["max_ast_nodes"]
    count = len(by_size[1])
    for size in range(3, max_nodes + 1, 2):
        output, seen = [], set()
        for left_size in range(1, size - 1, 2):
            right_size = size - 1 - left_size
            for left, right in product(by_size[left_size], by_size[right_size]):
                ls, rs = _signature(left, types), _signature(right, types)
                for op in spec["operators"]:
                    if op == "EDGE":
                        continue
                    if op == "PATH" and ls[1] != rs[0]:
                        continue
                    if op == "AND":
                        if ls != rs:
                            continue
                        # Commutative AND is canonicalized to avoid spurious ambiguity.
                        if _canonical(left) >= _canonical(right):
                            continue
                    ast = {"op": op, "left": left, "right": right}
                    key = _canonical(ast)
                    if key in seen:
                        continue
                    seen.add(key)
                    output.append(ast)
                    count += 1
                    if count > spec["max_candidates"]:
                        return [], count
        by_size[size] = output
    return [ast for size in sorted(by_size) for ast in by_size[size]], count


def induce_typed_rule(source: dict, examples: list[dict], grammar: dict) -> dict:
    facts = _validate(source)
    labels = _read_labels(examples)
    spec = _grammar(grammar, facts)
    if not any(x["positive"] for x in labels) or not any(
            not x["positive"] for x in labels):
        raise ValueError("Positive and negative labels required")
    result = {"schema": RULE_SCHEMA, "training_source_sha256": digest(source),
              "training_labels_sha256": digest(labels), "grammar_sha256": digest(spec),
              "qualityrag_admission": "INCONCLUSIVE",
              "packspec_completeness": "UNKNOWN",
              "source_authenticity": "UNVERIFIED"}
    expressions, count = _enumerate(spec)
    result["enumerated_candidates"] = count
    if count > spec["max_candidates"]:
        result.update(status="UNKNOWN", reason="CANDIDATE_BUDGET_EXCEEDED")
    else:
        matches = []
        work = [0]
        try:
            for ast in expressions:
                # Source facts are not type-checked here: declarations are hypotheses.
                scored = _score(_evaluate_relations(facts, ast, work), labels)
                if all(x["match"] for x in scored):
                    matches.append((ast, scored))
            if not matches:
                result.update(status="UNKNOWN", reason="NO_CONSISTENT_TYPED_AST")
            else:
                minimum = min(_nodes(ast) for ast, _ in matches)
                best = [(ast, scores) for ast, scores in matches if _nodes(ast) == minimum]
                if len(best) != 1:
                    result.update(status="UNKNOWN", reason="AMBIGUOUS_MINIMUM",
                                  minimal_candidate_count=len(best))
                else:
                    ast, scores = best[0]
                    result.update(status="CANDIDATE", ast=ast, ast_nodes=minimum,
                                  result_type=list(_signature(ast, spec["predicate_types"])),
                                  training_witnesses=scores, structural_training_verdict="SAT")
        except OverflowError:
            result.update(status="UNKNOWN", reason="EVALUATION_BUDGET_EXCEEDED")
        result["evaluation_work_units"] = work[0]
    result["fingerprint"] = digest(result)
    return result


def _nodes(ast: dict) -> int:
    return 1 if ast["op"] == "EDGE" else 1 + _nodes(ast["left"]) + _nodes(ast["right"])


def validate_typed_rule(training: dict, rule: dict, heldout: dict,
                        examples: list[dict], grammar: dict) -> dict:
    _validate(training)
    facts = _validate(heldout)
    labels = _read_labels(examples)
    spec = _grammar(grammar, facts)
    if digest(training) == digest(heldout):
        raise ValueError("Heldout graph must be distinct")
    body = dict(rule) if isinstance(rule, dict) else {}
    fingerprint = body.pop("fingerprint", None)
    if (fingerprint != digest(body) or body.get("schema") != RULE_SCHEMA
            or body.get("status") != "CANDIDATE"
            or body.get("training_source_sha256") != digest(training)
            or body.get("grammar_sha256") != digest(spec)
            or body.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Tampered or untrusted rule")
    _validate_ast(rule["ast"])
    if list(_signature(rule["ast"], spec["predicate_types"])) != rule["result_type"]:
        raise ValueError("Rule type mismatch")
    work = [0]
    try:
        witnesses = _score(_evaluate_relations(facts, rule["ast"], work), labels)
        failures = [x for x in witnesses if not x["match"]]
        state, verdict = ("COUNTEREXAMPLE", "UNSAT") if failures else ("FINITE_GRAPH_MATCH", "SAT")
    except OverflowError:
        witnesses, failures, state, verdict = [], [], "UNKNOWN", "UNKNOWN"
    result = {"schema": "rct.typed-rule-validation/v1.4",
              "rule_sha256": fingerprint, "grammar_sha256": digest(spec),
              "heldout_source_sha256": digest(heldout),
              "heldout_labels_sha256": digest(labels),
              "status": state, "finite_graph_verdict": verdict,
              "witnesses": witnesses, "counterexamples": failures,
              "evaluation_work_units": work[0], "qualityrag_admission": "INCONCLUSIVE",
              "domain_semantics": "UNVERIFIED"}
    result["fingerprint"] = digest(result)
    return result


def compile_typed_lens(heldout: dict, *, rule: dict, assessment: dict,
                       grammar: dict, lens_id: str, purpose: str) -> dict:
    _validate(heldout)
    _grammar(grammar, heldout["facts"])
    if not _ident(lens_id) or not _ident(purpose):
        raise ValueError("Lens identity and purpose required")
    r = dict(rule) if isinstance(rule, dict) else {}
    rf = r.pop("fingerprint", None)
    a = dict(assessment) if isinstance(assessment, dict) else {}
    af = a.pop("fingerprint", None)
    if (rf != digest(r) or r.get("status") != "CANDIDATE"
            or r.get("schema") != RULE_SCHEMA
            or r.get("grammar_sha256") != digest(grammar)
            or r.get("qualityrag_admission") != "INCONCLUSIVE"
            or af != digest(a) or a.get("rule_sha256") != rf
            or a.get("grammar_sha256") != digest(grammar)
            or a.get("heldout_source_sha256") != digest(heldout)
            or a.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Rule, grammar or assessment fingerprint mismatch")
    lens = {"schema": "rct.source-lens/v0.6", "lens_id": lens_id,
            "purpose": purpose, "source_sha256": digest(heldout),
            "required": ["declared_typed_structural_relations"],
            "permitted_omissions": [],
            "candidate_claims": [{
                "subject": w["subject"], "object": w["object"],
                "fact_witness": w["fact_witness"], "label_source_ref": w["label_source_ref"],
                "status": "UNVERIFIED_SOURCE_CLAIM"}
                for w in assessment["witnesses"]],
            "candidate_grammar": rule, "evaluation": assessment,
            "unresolved": ([] if assessment["finite_graph_verdict"] == "SAT"
                           else ["unverified_or_failed_validation"]),
            "local_coverage": ("LABELED_FINITE_GRAPH_CHECKED" if
                               assessment["finite_graph_verdict"] == "SAT" else "UNKNOWN"),
            "qualityrag_admission": "INCONCLUSIVE",
            "source_authenticity": "UNVERIFIED", "packspec_completeness": "UNKNOWN",
            "grammar": "DECLARATIVE_TYPED_OPERATOR_AST",
            "limitations": ["Typed signatures are declarations, not authenticated facts",
                            "Finite graph labels are not world truth",
                            "Operator set predefined; no novel mathematical invention",
                            "FF-RCT and PackSpec verification not executed"]}
    lens["fingerprint"] = digest(lens)
    return lens
