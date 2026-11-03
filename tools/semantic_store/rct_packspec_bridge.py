"""RCT v1.6 bridge to the *existing* QualityRag unified PackSpec gate.

The reviewed ConstraintIR source and graph source have separate fingerprints.
A caller-supplied binding can associate them for an experiment, but it does
not authenticate either source, approve omissions, or attest semantic truth.
We reuse canonical evaluate_unified, with NO host attestation capability,
and never return ADMIT/can_generate from this research adapter.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

_PACKSPEC = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_PACKSPEC) not in sys.path:
    sys.path.insert(0, str(_PACKSPEC))

from unified_gate import evaluate_unified, UnifiedGateError
from typed_ir import IR_SCHEMA
from store import digest

BINDING_SCHEMA = "rct.packspec-binding/v1.6"
RECEIPT_SCHEMA = "rct.governance-bridge/v1.6"


def bind_candidate(lens: dict, ir: dict, *, purpose: str) -> dict:
    """Record an *unverified* association; never authenticate it."""
    if not isinstance(lens, dict) or not isinstance(ir, dict):
        raise ValueError("Lens and typed IR required")
    if (lens.get("qualityrag_admission") != "INCONCLUSIVE"
            or lens.get("purpose") != purpose
            or not isinstance(purpose, str) or not purpose):
        raise ValueError("Mismatched purpose or admitted lens")
    body = dict(lens)
    lf = body.pop("fingerprint", None)
    if lf != digest(body):
        raise ValueError("Mutated lens")
    if ir.get("schema") != IR_SCHEMA:
        raise ValueError("Canonical reviewed ConstraintIR required")
    binding = {
        "schema": BINDING_SCHEMA,
        "lens_fingerprint": lf,
        "graph_source_sha256": lens["source_sha256"],
        "packspec_ir_sha256": ir["ir_sha256"],
        "packspec_source_sha256": ir["source"]["sha256"],
        "purpose": purpose,
        "authentication": "UNVERIFIED_CALLER_BINDING",
        "omission_authorization": "NOT_ESTABLISHED",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    binding["fingerprint"] = digest(binding)
    return binding


def evaluate_bound_lens(lens: dict, ir: dict, binding: dict,
                        witnesses: list[dict], observations: dict,
                        as_of: str) -> dict[str, Any]:
    """Call the actual unified gate and preserve independent RCT blockers.

    A canonical gate REFUSE is reflected as REFUSE; all other outcomes stay
    INCONCLUSIVE because the RCT-specific omission/meaning contract has not
    been independently reviewed or authenticated.
    """
    if not all(isinstance(x, dict) for x in (lens, ir, binding)):
        raise ValueError("Lens, IR and binding required")
    lb, bb = dict(lens), dict(binding)
    lf, bf = lb.pop("fingerprint", None), bb.pop("fingerprint", None)
    if (lf != digest(lb) or bf != digest(bb)
            or lens.get("qualityrag_admission") != "INCONCLUSIVE"
            or binding.get("schema") != BINDING_SCHEMA
            or binding.get("lens_fingerprint") != lf
            or binding.get("graph_source_sha256") != lens.get("source_sha256")
            or binding.get("packspec_ir_sha256") != ir.get("ir_sha256")
            or binding.get("packspec_source_sha256") != ir.get("source", {}).get("sha256")
            or binding.get("purpose") != lens.get("purpose")
            or binding.get("authentication") != "UNVERIFIED_CALLER_BINDING"
            or binding.get("omission_authorization") != "NOT_ESTABLISHED"
            or binding.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Binding identity or evidence mismatch")

    # Canonical QualityRag evaluator is the only policy evaluator here.
    # Passing NO verifier is intentional; the bridge cannot authenticate
    # external sources or invent signed reviewer/attestor authority.
    decision = evaluate_unified(ir, witnesses, observations, as_of,
                                verify_attestation=None)
    blockers = [
        "PACKSPEC_TO_LENS_PURPOSE_SEMANTIC_MAPPING_UNVERIFIED",
        "SOURCE_AND_REVIEW_AUTHORITY_UNVERIFIED",
        "RCT_LENS_SEMANTIC_SUFFICIENCY_NOT_ESTABLISHED",
    ]
    if lens.get("omitted_fact_ids"):
        blockers.append("OMISSION_AUTHORIZATION_NOT_ESTABLISHED")
    if decision["verdict"] != "ADMIT":
        blockers.append("CANONICAL_GATE_" + decision["verdict"])
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "binding_sha256": bf,
        "lens_fingerprint": lf,
        "packspec_ir_sha256": ir["ir_sha256"],
        "source_sha256": lens["source_sha256"],
        "canonical_gate": decision,
        "canonical_checks_verdict": decision["checks_verdict"],
        "verdict": "REFUSE" if decision["verdict"] == "REFUSE" else "INCONCLUSIVE",
        "can_generate": False,
        "blockers": blockers,
        "scope": "INTEGRATION_DIAGNOSTIC_ONLY",
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt


def guarded_candidate_use(lens: dict, ir: dict, binding: dict,
                          witnesses: list[dict], observations: dict,
                          as_of: str, generator) -> dict:
    """Fail closed: no candidate-lens generation path is authorized in v1.6."""
    if not callable(generator):
        raise ValueError("Generator required")
    receipt = evaluate_bound_lens(lens, ir, binding, witnesses, observations, as_of)
    return {"decision": receipt, "generated": False, "answer": None}
