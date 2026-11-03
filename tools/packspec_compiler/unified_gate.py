"""Unified fail-closed gate over a reviewed IR, evidence and bounded semantic checks.

No semantic truth is inferred from metadata or review labels. No answer can be
generated without a host-supplied attestation verifier and full admission.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any
import sys
from pathlib import Path

# Imported as a standalone compiler module; sdk/python is a sibling repo path.
_SDK = Path(__file__).resolve().parents[2] / "sdk" / "python"
if str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from qualityrag import evaluate as evaluate_evidence
from semantic_runtime import evaluate_semantics
from typed_ir import IR_SCHEMA, _fingerprint

SCHEMA = "qualityrag.unified-decision/v1"
VERDICTS = frozenset(("ADMIT", "REFUSE", "INCONCLUSIVE"))

class UnifiedGateError(ValueError):
    pass

def _checked_ir(ir: dict) -> tuple[list[dict], list[dict]]:
    if not isinstance(ir, dict) or ir.get("schema") != IR_SCHEMA:
        raise UnifiedGateError("Typed IR is required")
    source = ir.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("sha256"), str) or len(source["sha256"]) != 64:
        raise UnifiedGateError("Missing source identity")
    nodes = ir.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 240:
        raise UnifiedGateError("Empty or invalid IR nodes")
    if _fingerprint({"source_sha256": source["sha256"], "nodes": nodes}) != ir.get("ir_sha256"):
        raise UnifiedGateError("IR fingerprint mismatch")
    seen_nodes, seen_requirements = set(), set()
    evidence_nodes, semantic_nodes = [], []
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("node_id"), str):
            raise UnifiedGateError("Invalid IR node")
        if n["node_id"] in seen_nodes:
            raise UnifiedGateError("Duplicate IR node")
        seen_nodes.add(n["node_id"])
        if n.get("review", {}).get("approved") is not True or n.get("source", {}).get("source_sha256") != source["sha256"]:
            raise UnifiedGateError("Unreviewed or source-mismatched node")
        if n.get("kind") == "EVIDENCE_PRESENCE":
            if n.get("runtime") != "METADATA_GATE_V0_1" or n.get("status") != "PROJECTION_ONLY":
                raise UnifiedGateError("Unbound evidence projection")
            params = n.get("parameters", {})
            rid, count = params.get("requirement_id"), params.get("min_independent_sources")
            if not isinstance(rid, str) or not rid or type(count) is not int or count < 1:
                raise UnifiedGateError("Invalid evidence projection")
            if rid in seen_requirements:
                raise UnifiedGateError("Duplicate evidence obligation")
            seen_requirements.add(rid)
            evidence_nodes.append(n)
        else:
            semantic_nodes.append(n)
    summary = ir.get("summary", {})
    if (not isinstance(summary, dict) or summary.get("total") != len(nodes) or
        summary.get("evidence_presence_projections") != len(evidence_nodes) or
        summary.get("deferred_semantic_constraints") != len(semantic_nodes)):
        raise UnifiedGateError("IR inventory mismatch")
    return evidence_nodes, semantic_nodes

def _semantic_subset(ir: dict, nodes: list[dict]) -> dict:
    """Reuse the exact reviewed runtime rather than inventing a second evaluator."""
    subset = {**ir, "nodes": deepcopy(nodes)}
    subset["ir_sha256"] = _fingerprint({
        "source_sha256": ir["source"]["sha256"], "nodes": subset["nodes"]
    })
    return subset

def evaluate_unified(
    ir: dict,
    witnesses: list[dict],
    observations: dict,
    as_of: str,
    *,
    verify_attestation: Callable[[dict, list[dict], dict], bool] | None = None,
) -> dict:
    """Evaluate all declared IR nodes and gate on explicit host evidence attestation.

    Host verifier receives (source identity, witnesses, observations). It must
    perform actual provenance authentication. A mere 'True' stub is insecure.
    A missing/failing verifier leaves otherwise valid checks INCONCLUSIVE.
    """
    evidence_nodes, semantic_nodes = _checked_ir(ir)
    evidence_receipt: dict[str, Any]
    if evidence_nodes:
        policy = {
            "id": "unified-" + ir["source"]["sha256"][:16],
            "version": "1",
            "requirements": [{
                "id": n["parameters"]["requirement_id"],
                "min_independent_sources": n["parameters"]["min_independent_sources"],
            } for n in evidence_nodes],
        }
        evidence_receipt = evaluate_evidence(policy, witnesses, as_of=as_of)
        ev_verdict = evidence_receipt["verdict"]
    else:
        evidence_receipt = {"verdict": "NOT_APPLICABLE", "findings": [], "reason": "NO_EVIDENCE_NODES"}
        ev_verdict = "NOT_APPLICABLE"
    if semantic_nodes:
        semantic_receipt = evaluate_semantics(_semantic_subset(ir, semantic_nodes), observations, as_of)
        sem_verdict = semantic_receipt["verdict"]
    else:
        semantic_receipt = {"verdict": "NOT_APPLICABLE", "findings": [], "reason": "NO_SEMANTIC_NODES"}
        sem_verdict = "NOT_APPLICABLE"

    all_results = (ev_verdict, sem_verdict)
    if "REFUSE" in all_results:
        checks_verdict = "REFUSE"
    elif "INCONCLUSIVE" in all_results:
        checks_verdict = "INCONCLUSIVE"
    else:
        checks_verdict = "ADMIT"

    attested = False
    attestation_error = None
    # Never run an external attestation callback if a required check already failed.
    if checks_verdict == "ADMIT" and verify_attestation is not None:
        try:
            attested = verify_attestation(ir["source"], witnesses, observations) is True
        except Exception:
            attestation_error = "HOST_ATTESTATION_ERROR"

    overall = checks_verdict if checks_verdict != "ADMIT" else ("ADMIT" if attested else "INCONCLUSIVE")
    return {
        "schema": SCHEMA,
        "verdict": overall,
        "checks_verdict": checks_verdict,
        "can_generate": overall == "ADMIT",
        "attestation": "HOST_VERIFIED" if attested else (
            attestation_error or "MISSING_OR_FAILED_HOST_ATTESTATION"),
        "ir_sha256": ir["ir_sha256"],
        "source_sha256": ir["source"]["sha256"],
        "coverage": {"declared_nodes": len(ir["nodes"]),
                     "evidence_nodes": len(evidence_nodes),
                     "semantic_nodes": len(semantic_nodes)},
        "evidence": evidence_receipt,
        "semantics": semantic_receipt,
        "limitations": "Host attestation is application-supplied; no source completeness or document truth is proven",
    }

def guarded_generate(
    ir: dict, witnesses: list[dict], observations: dict, as_of: str,
    generator: Callable[[], Any],
    *,
    verify_attestation: Callable[[dict, list[dict], dict], bool] | None = None,
) -> dict:
    """Exactly one decision before invoking generator. Never call it on non-ADMIT."""
    if not callable(generator):
        raise UnifiedGateError("Generator must be callable")
    receipt = evaluate_unified(ir, witnesses, observations, as_of,
                               verify_attestation=verify_attestation)
    if not receipt["can_generate"]:
        return {"decision": receipt, "answer": None, "generated": False}
    return {"decision": receipt, "answer": generator(), "generated": True}
