"""Typed, non-executable constraint IR for inspected APX PackSpec clauses.

Bounded source mapping with epistemic guardrails:
- all nodes are explicitly reviewed and source-hash pinned
- only EVIDENCE_PRESENCE can project to the QualityRag v0.1 metadata gate
- TEMPORAL, AUTHORITY, PREDICATE and PROBE stay DEFERRED (never evaluated)
- there is no interpretation of free-form prose as executable expressions
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any

IR_SCHEMA = "qualityrag.constraint-ir/v1"
TYPED_MAPPING_SCHEMA = "qualityrag.typed-mapping/v1"
ALLOWED_KINDS = frozenset({"EVIDENCE_PRESENCE", "TEMPORAL", "AUTHORITY", "PROBE", "PREDICATE"})
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")

class IRValidationError(ValueError):
    pass

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IRValidationError(message)

def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf8")).hexdigest()

def _identifier(v: Any, what: str) -> str:
    _require(isinstance(v, str) and bool(ID_RE.fullmatch(v)), "Invalid " + what)
    return v

def _review_rule(rule: dict, lookup: dict[str, dict]) -> tuple[dict, dict]:
    _require(isinstance(rule, dict) and rule.get("approved") is True, "Explicit review approval required")
    reviewer = rule.get("reviewed_by")
    rationale = rule.get("rationale")
    _require(isinstance(reviewer, str) and bool(reviewer.strip()), "Reviewer label required")
    _require(isinstance(rationale, str) and len(rationale.strip()) >= 12, "Substantive rationale required")
    source = lookup.get(rule.get("candidate_id"))
    _require(source is not None, "Unknown source candidate")
    kind = rule.get("kind")
    _require(kind in ALLOWED_KINDS, "Unsupported IR kind")
    return source, {
        "reviewed_by": reviewer.strip(),
        "rationale": rationale.strip(),
        "approved": True,
        "authentication": "UNVERIFIED_REVIEWER_LABEL",
    }

def compile_ir(report: dict, mapping: dict) -> dict:
    """Compile explicit mappings into typed *records*, not executable semantic rules."""
    _require(report.get("schema") == "qualityrag.source-inspection/v1", "Invalid inspection report")
    _require(mapping.get("schema") == TYPED_MAPPING_SCHEMA, "Invalid typed mapping schema")
    _require(mapping.get("source_sha256") == report.get("source", {}).get("sha256"),
             "Source fingerprint mismatch")
    _require(report.get("limits", {}).get("truncated") is False,
             "Truncated inspection cannot be certified complete")
    candidates = report.get("candidate_constraints")
    _require(isinstance(candidates, list), "Missing source constraints")
    lookup = {x["candidate_id"]: x for x in candidates}
    _require(len(lookup) == len(candidates), "Duplicate source candidate identifiers")
    rules = mapping.get("rules")
    _require(isinstance(rules, list) and bool(rules), "No typed mapping rules")
    nodes = []
    seen = set()
    for rule in rules:
        source, review = _review_rule(rule, lookup)
        node_id = _identifier(rule.get("node_id"), "node identifier")
        _require(node_id not in seen, "Duplicate node identifier")
        seen.add(node_id)
        kind = rule["kind"]
        params = rule.get("parameters")
        _require(isinstance(params, dict), "Typed parameters object required")
        if kind == "EVIDENCE_PRESENCE":
            requirement_id = _identifier(params.get("requirement_id"), "evidence requirement identifier")
            count = params.get("min_independent_sources", 1)
            _require(type(count) is int and 1 <= count <= 20, "Invalid independent source count")
            typed = {"requirement_id": requirement_id, "min_independent_sources": count}
            runtime = "METADATA_GATE_V0_1"
            posture = "PROJECTION_ONLY"
        elif kind == "TEMPORAL":
            relation = params.get("relation")
            _require(relation in ("BEFORE", "AFTER", "WITHIN", "EXPIRES_AT"), "Invalid temporal relation")
            anchor = _identifier(params.get("anchor"), "time anchor")
            if relation == "WITHIN":
                duration = params.get("duration_seconds")
                _require(type(duration) is int and 1 <= duration <= 31_536_000,
                         "Invalid temporal interval")
                typed = {"relation": relation, "anchor": anchor, "duration_seconds": duration}
            else:
                typed = {"relation": relation, "anchor": anchor}
            runtime = "NOT_IMPLEMENTED"
            posture = "DEFERRED"
        elif kind == "AUTHORITY":
            role = _identifier(params.get("role"), "authority role")
            scope = params.get("scope")
            _require(isinstance(scope, str) and bool(scope.strip()) and len(scope) <= 300,
                     "Authority scope required")
            typed = {"role": role, "scope": scope.strip(), "applicability": "REQUIRES_SOURCE_VALIDATION"}
            runtime = "NOT_IMPLEMENTED"
            posture = "DEFERRED"
        elif kind == "PROBE":
            probe_id = _identifier(params.get("probe_id"), "probe identifier")
            artifact_type = params.get("artifact_type")
            _require(artifact_type in ("OBSERVATION", "TEST_RESULT", "PRIMARY_RECORD"),
                     "Unsupported probe artifact type")
            typed = {"probe_id": probe_id, "artifact_type": artifact_type,
                     "executor": "UNBOUND", "result": "UNMEASURED"}
            runtime = "NOT_IMPLEMENTED"
            posture = "DEFERRED"
        else:
            expression = params.get("expression")
            _require(isinstance(expression, str) and expression.strip() and len(expression) <= 1600,
                     "Predicate expression required")
            typed = {"expression": expression, "language": "UNTRUSTED_TEXT",
                     "interpretation": "NOT_COMPILED"}
            runtime = "NOT_IMPLEMENTED"
            posture = "DEFERRED"
        nodes.append({
            "node_id": node_id,
            "kind": kind,
            "status": posture,
            "runtime": runtime,
            "parameters": typed,
            "source": {
                "candidate_id": source["candidate_id"],
                "location": source["location"],
                "quotation": source["quotation"],
                "quotation_sha256": source["quotation_sha256"],
                "source_sha256": report["source"]["sha256"],
            },
            "review": review,
        })

    # Ensure a single namespace for approved evidence requirements.
    requirements = [n["parameters"]["requirement_id"] for n in nodes if n["kind"] == "EVIDENCE_PRESENCE"]
    _require(len(requirements) == len(set(requirements)), "Duplicate evidence obligation")

    summary = {
        "total": len(nodes),
        "evidence_presence_projections": len(requirements),
        "deferred_semantic_constraints": len(nodes) - len(requirements),
        "semantic_constraints_executed": 0,
    }
    return {
        "schema": IR_SCHEMA,
        "source": report["source"],
        "nodes": nodes,
        "summary": summary,
        "scope": "INSPECTION_DERIVED_CANDIDATES_ONLY",
        "assurance": "NO_AUTOMATIC_SEMANTIC_ENFORCEMENT",
        "ir_sha256": _fingerprint({"source_sha256": report["source"]["sha256"], "nodes": nodes}),
    }

def project_gate(ir: dict, policy_id: str, version: str = "1.0") -> dict:
    """Project only reviewed evidence requirements; fail if all constraints are deferred."""
    _require(ir.get("schema") == IR_SCHEMA, "Unsupported IR schema")
    _identifier(policy_id, "policy id")
    _require(isinstance(version, str) and bool(version.strip()), "Invalid policy version")
    nodes = ir.get("nodes")
    _require(isinstance(nodes, list), "Missing typed nodes")
    reviewed = []
    for node in nodes:
        _require(node.get("review", {}).get("approved") is True and
                 node.get("source", {}).get("source_sha256") == ir.get("source", {}).get("sha256"),
                 "Unreviewed or mismatched typed node")
        if node.get("kind") == "EVIDENCE_PRESENCE":
            _require(node.get("runtime") == "METADATA_GATE_V0_1" and node.get("status") == "PROJECTION_ONLY",
                     "Invalid metadata projection posture")
            reviewed.append({"id": node["parameters"]["requirement_id"],
                             "min_independent_sources": node["parameters"]["min_independent_sources"]})
    _require(bool(reviewed), "No enforceable evidence-presence projections")
    _require(ir.get("summary", {}).get("deferred_semantic_constraints") ==
             sum(n.get("kind") != "EVIDENCE_PRESENCE" for n in nodes),
             "IR deferred-constraint inventory mismatch")
    return {
        "policy": {"id": policy_id, "version": version, "requirements": reviewed},
        "semantic_authorization": "NOT_ESTABLISHED",
        "deferred_constraints": [
            {"node_id": n["node_id"], "kind": n["kind"], "status": n["status"]}
            for n in nodes if n["kind"] != "EVIDENCE_PRESENCE"
        ],
        "source_sha256": ir["source"]["sha256"],
        "ir_sha256": ir["ir_sha256"],
        "notice": "ADMIT checks declared evidence presence only, not deferred APX semantics",
    }

def draft_typed_mapping(report: dict, limit: int = 15) -> dict:
    """Generate an inert review template, never approved by construction."""
    return {
        "schema": TYPED_MAPPING_SCHEMA,
        "source_sha256": report["source"]["sha256"],
        "rules": [
            {"candidate_id": c["candidate_id"], "node_id": f"review-{c['candidate_id']}",
             "kind": "EVIDENCE_PRESENCE", "parameters": {"requirement_id": ""},
             "approved": False, "reviewed_by": "", "rationale": ""}
            for c in report["candidate_constraints"][:limit]
        ],
        "warning": "Kind is merely a placeholder. Reviewer must select kind, parameters and confirm source meaning.",
    }
