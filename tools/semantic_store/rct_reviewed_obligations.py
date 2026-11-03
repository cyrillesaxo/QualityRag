"""Reviewed semantic-obligation binding for an RCT candidate (v2).

A host-trusted reviewer signs an exact PackSpec-to-lens mapping using the
existing QualityRag Ed25519 signed-observation format. This establishes record
integrity and configured-key authorship, not semantic truth, source authority,
or machine-verified completeness. Never emit ADMIT for this research adapter.
"""
from __future__ import annotations

from pathlib import Path
import sys

_PACKSPEC = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_PACKSPEC) not in sys.path:
    sys.path.insert(0, str(_PACKSPEC))
from signed_bundles import verify, verify_policy, verify_attestation, ATTEST_SCHEMA, SignatureError
from typed_ir import _fingerprint
from store import digest

SCHEMA = "rct.reviewed-obligations/v2"


def proposed_review_record(lens: dict, ir: dict, conservation: dict) -> dict:
    """Inert review draft. A reviewer must inspect and sign it externally."""
    if not isinstance(lens, dict) or not isinstance(ir, dict) or not isinstance(conservation, dict):
        raise ValueError("Lens, IR and conservation result required")
    l, c = dict(lens), dict(conservation)
    lens_hash = l.pop("fingerprint", None)
    conservation_hash = c.pop("fingerprint", None)
    if (lens_hash != digest(l)
            or conservation_hash != digest(c)
            or conservation.get("finite_structural_verdict") != "SAT"
            or conservation.get("lens_fingerprint") != lens_hash
            or ir.get("ir_sha256") != _fingerprint({
                "source_sha256": ir.get("source", {}).get("sha256"),
                "nodes": ir.get("nodes")})
            or lens.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Invalid typed governance inputs")
    nodes = ir.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Empty governing IR")
    return {
        "schema": SCHEMA,
        "lens_fingerprint": lens_hash,
        "source_sha256": lens["source_sha256"],
        "packspec_source_sha256": ir["source"]["sha256"],
        "packspec_ir_sha256": ir["ir_sha256"],
        "conservation_receipt_sha256": conservation_hash,
        "purpose": lens["purpose"],
        "required_distinctions": sorted(lens["required"]),
        "permitted_omissions": sorted(lens["permitted_omissions"]),
        "omitted_fact_ids": sorted(lens["omitted_fact_ids"]),
        "reviewed_ir_node_ids": sorted(n["node_id"] for n in nodes),
        "review_scope": "FINITE_DECLARED_OPERATOR_AND_SOURCE_ONLY",
        "review_verdict": "REVIEW_REQUIRED",
        "semantic_completeness": "UNDETERMINED",
    }


def verify_reviewed_mapping(*, lens: dict, ir: dict, conservation: dict,
                            signed_policy: dict, signed_review: dict,
                            reviewer_keys: dict, policy_keys: dict, minimum_sequence: int,
                            service: str, environment: str,
                            as_of: str, nonce_accepted) -> dict:
    """Verify signed exact obligations; keep quality assurance INCONCLUSIVE."""
    expected = proposed_review_record(lens, ir, conservation)
    if not isinstance(signed_review, dict) or not isinstance(signed_policy, dict):
        raise ValueError("Signed review/policy required")
    verified_policy = verify_policy(
        signed_policy, policy_keys, service=service,
        environment=environment, as_of=as_of,
        minimum_sequence=minimum_sequence)
    if verified_policy.get("ir") != ir:
        raise ValueError("Signed reviewed policy must match exact governing IR")
    if (signed_review.get("key_id") == signed_policy.get("key_id")
            or signed_review.get("key_id") not in reviewer_keys):
        raise SignatureError("Reviewer must use a separately trusted identity")
    payload = verify(signed_review, reviewer_keys, schema=ATTEST_SCHEMA)
    if payload.get("witnesses") != []:
        raise ValueError("Reviewer envelope cannot smuggle evidence witnesses")
    observations = payload.get("observations")
    if not isinstance(observations, dict) or set(observations) != {"rct_semantic_review"}:
        raise ValueError("Explicit RCT semantic review required")
    signed_record = observations["rct_semantic_review"]
    if not isinstance(signed_record, dict):
        raise ValueError("Invalid reviewed obligation record")
    # The reviewer must expressly acknowledge finite scope. It is a review
    # authorization assertion only and does not certify full semantic safety.
    agreed = dict(expected)
    agreed["review_verdict"] = "REVIEWED_FINITE_SCOPE"
    if signed_record != agreed:
        raise ValueError("Missing, changed, or over-broad reviewed obligation mapping")
    verified = verify_attestation(
        signed_review, reviewer_keys,
        policy_signature=signed_policy["signature"],
        service=service, environment=environment, as_of=as_of,
        witnesses=[], observations={"rct_semantic_review": agreed},
        nonce_accepted=nonce_accepted)
    if verified is not True:
        raise SignatureError("Review signature/replay not accepted")
    receipt = {
        "schema": SCHEMA,
        "lens_fingerprint": lens["fingerprint"],
        "source_sha256": lens["source_sha256"],
        "packspec_ir_sha256": ir["ir_sha256"],
        "conservation_receipt_sha256": conservation["fingerprint"],
        "review_key_id": signed_review["key_id"],
        "declared_review_scope": agreed["review_scope"],
        "review_record_signature": "VERIFIED",
        "reviewed_node_count": len(agreed["reviewed_ir_node_ids"]),
        "reviewed_required_count": len(agreed["required_distinctions"]),
        "reviewed_omission_count": len(agreed["omitted_fact_ids"]),
        "semantic_completeness": "UNKNOWN",
        "omission_safety": "NOT_INDEPENDENTLY_PROVEN",
        "verdict": "INCONCLUSIVE",
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt
