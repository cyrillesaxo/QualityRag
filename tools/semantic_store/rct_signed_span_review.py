"""Signed reviewer binding for an exact RCT source-span obligation inventory.

Reuses QualityRag's canonical signed-policy and signed-attestation verifier.
An authenticated reviewer signature binds records to the approved policy,
source/candidate hashes, and lens identity. It does NOT prove inventory
completeness, truthful values, or semantic equivalence; never authorizes ADMIT.
"""
from __future__ import annotations

from pathlib import Path
import sys

_PACKSPEC = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_PACKSPEC) not in sys.path:
    sys.path.insert(0, str(_PACKSPEC))

from signed_bundles import (
    ATTEST_SCHEMA, SignatureError, verify, verify_policy, verify_attestation)
from store import digest

SCHEMA = "rct.signed-source-span-inventory/v2.2"


def proposed_inventory_review(joined: dict, ir: dict) -> dict:
    if not isinstance(joined, dict) or not isinstance(ir, dict):
        raise ValueError("Joined source-span candidate and reviewed IR required")
    body = dict(joined)
    fp = body.pop("fingerprint", None)
    if (fp != digest(body)
            or joined.get("schema") != "rct.source-span-joined-candidate/v2.1"
            or joined.get("qualityrag_admission") != "INCONCLUSIVE"
            or joined.get("can_generate") is not False):
        raise ValueError("Untrusted joined source-span candidate")
    audit = joined.get("source_span_audit")
    if not isinstance(audit, dict):
        raise ValueError("Missing source-span audit")
    a = dict(audit)
    af = a.pop("fingerprint", None)
    if (af != digest(a)
            or audit.get("schema") != "rct.source-span-conservation/v2.1"
            or audit.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Untrusted audit receipt")
    from typed_ir import _fingerprint
    if (ir.get("ir_sha256") != _fingerprint({
            "source_sha256": ir.get("source", {}).get("sha256"),
            "nodes": ir.get("nodes")})
            or not isinstance(ir.get("nodes"), list)
            or not ir["nodes"]):
        raise ValueError("Invalid reviewed ConstraintIR")
    return {
        "schema":SCHEMA,
        "joined_candidate_fingerprint":fp,
        "structural_fingerprint":joined["structural_fingerprint"],
        "span_audit_fingerprint":af,
        "source_text_sha256":audit["source_sha256"],
        "candidate_text_sha256":audit["candidate_sha256"],
        "obligation_inventory_sha256":audit["reviewed_inventory_sha256"],
        "governing_ir_sha256":ir["ir_sha256"],
        "governing_packspec_source_sha256":ir["source"]["sha256"],
        "governing_ir_nodes":sorted(n["node_id"] for n in ir["nodes"]),
        "review_scope":"EXACT_SUPPLIED_SPANS_AND_TYPED_VALUES_ONLY",
        "review_status":"REVIEW_REQUIRED",
        "completeness":"UNKNOWN",
        "omission_authority":"NOT_ESTABLISHED",
    }


def verify_inventory_review(*, joined: dict, ir: dict, signed_policy: dict,
                            signed_review: dict, policy_keys: dict,
                            reviewer_keys: dict, minimum_sequence: int,
                            service: str, environment: str, as_of: str,
                            nonce_accepted) -> dict:
    draft=proposed_inventory_review(joined, ir)
    if not isinstance(signed_policy, dict) or not isinstance(signed_review, dict):
        raise ValueError("Signed policy and review required")
    checked=verify_policy(
        signed_policy, policy_keys, service=service,
        environment=environment, as_of=as_of,
        minimum_sequence=minimum_sequence)
    if checked["ir"] != ir:
        raise ValueError("Signed PackSpec IR mismatch")
    if (signed_review.get("key_id") == signed_policy.get("key_id")
            or signed_review.get("key_id") not in reviewer_keys):
        raise SignatureError("Review must use independently configured reviewer key")
    body=verify(signed_review, reviewer_keys, schema=ATTEST_SCHEMA)
    if body.get("witnesses") != []:
        raise ValueError("Review envelope cannot carry evidence witnesses")
    observation=body.get("observations")
    expected=dict(draft, review_status="REVIEWED_FINITE_SCOPE")
    if observation != {"source_span_inventory_review":expected}:
        raise ValueError("Review must bind exact inventory, candidate and PackSpec nodes")
    if verify_attestation(
            signed_review,reviewer_keys,
            policy_signature=signed_policy["signature"],
            service=service,environment=environment,as_of=as_of,
            witnesses=[],observations=observation,
            nonce_accepted=nonce_accepted) is not True:
        raise SignatureError("Reviewer attestation rejected")
    result={
        "schema":SCHEMA,
        "joined_candidate_fingerprint":joined["fingerprint"],
        "review_key_id":signed_review["key_id"],
        "signed_governing_ir_sha256":ir["ir_sha256"],
        "span_audit_fingerprint":joined["source_span_audit"]["fingerprint"],
        "review_signature":"VERIFIED",
        "verdict":"REFUSE" if joined["verdict"] == "REFUSE" else "INCONCLUSIVE",
        "completeness":"UNKNOWN",
        "omission_authority":"NOT_ESTABLISHED",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
    }
    result["fingerprint"]=digest(result)
    return result
