"""Joint RCT v1.7 diagnostics. Reuses the canonical gate and SDK WitnessGraph.

These are two independent policy projections until a trusted source-to-policy
link is implemented. Neither can authorize semantic omission or generation.
"""
from __future__ import annotations

from rct_packspec_bridge import evaluate_bound_lens
from rct_witness_bridge import evaluate_witness_coverage
from store import digest


def evaluate_joint_governance(*, lens: dict, reviewed_ir: dict, ir_binding: dict,
                              evidence_pack: dict, witness_mapping: dict,
                              witnesses: list[dict], observations: dict,
                              as_of: str) -> dict:
    # No attempt to convert evidence_pack findings to reviewed ConstraintIR nodes.
    canonical = evaluate_bound_lens(
        lens, reviewed_ir, ir_binding, witnesses, observations, as_of)
    coverage = evaluate_witness_coverage(
        lens, evidence_pack, witness_mapping, witnesses, as_of=as_of)
    verdict = ("REFUSE" if "REFUSE" in
               (canonical["verdict"], coverage["verdict"]) else "INCONCLUSIVE")
    blockers = sorted(set(canonical["blockers"] + coverage["blockers"] +
                          ["REVIEWED_IR_AND_EVIDENCE_PACK_SOURCE_BINDING_UNVERIFIED"]))
    result = {
        "schema": "rct.joint-governance/v1.7",
        "lens_fingerprint": lens["fingerprint"],
        "reviewed_ir_sha256": reviewed_ir["ir_sha256"],
        "witness_pack_sha256": digest(evidence_pack),
        "unified_gate_receipt_sha256": canonical["fingerprint"],
        "witness_coverage_receipt_sha256": coverage["fingerprint"],
        "unified_gate": canonical, "witness_coverage": coverage,
        "verdict": verdict, "can_generate": False,
        "qualityrag_admission": "INCONCLUSIVE",
        "blockers": blockers,
        "source_mapping": "UNVERIFIED_DISTINCT_POLICY_CONTEXTS",
    }
    result["fingerprint"] = digest(result)
    return result
