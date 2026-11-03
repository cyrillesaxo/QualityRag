"""Ed25519-reviewed typed role graph bound to exact source/candidate and PackSpec.

A signature authenticates the finite reviewer annotation, not the truth or
completeness of role parsing. Recomputes the underlying role audit from the
supplied original bytes before consuming the review nonce.
"""
from __future__ import annotations

from pathlib import Path
import sys

_P = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_P) not in sys.path:
    sys.path.insert(0, str(_P))

from signed_bundles import (
    ATTEST_SCHEMA, SignatureError, verify, verify_policy, verify_attestation)
from rct_role_grammar import audit_typed_role_graph
from store import digest

SCHEMA = "rct.signed-role-grammar-review/v0.1"


def proposed_role_review(*, source: str, candidate: str,
                         source_facts: list[dict], candidate_facts: list[dict],
                         ir: dict) -> dict:
    from hashlib import sha256
    from typed_ir import _fingerprint
    if (not isinstance(ir,dict) or not isinstance(ir.get("nodes"),list)
            or not ir["nodes"]
            or not isinstance(ir.get("source"),dict)
            or ir.get("ir_sha256") != _fingerprint({
                "source_sha256":ir["source"].get("sha256"),
                "nodes":ir["nodes"]})):
        raise ValueError("Reviewed PackSpec IR is invalid")
    audit = audit_typed_role_graph(
        source=source,candidate=candidate,
        source_facts=source_facts,candidate_facts=candidate_facts,
        source_sha256=sha256(source.encode()).hexdigest(),
        candidate_sha256=sha256(candidate.encode()).hexdigest(),
        source_inventory_sha256=digest(source_facts),
        candidate_inventory_sha256=digest(candidate_facts))
    return {
        "schema":SCHEMA,
        "audit_fingerprint":audit["fingerprint"],
        "source_sha256":audit["source_sha256"],
        "candidate_sha256":audit["candidate_sha256"],
        "source_inventory_sha256":audit["source_inventory_sha256"],
        "candidate_inventory_sha256":audit["candidate_inventory_sha256"],
        "governing_ir_sha256":ir["ir_sha256"],
        "governing_source_sha256":ir["source"]["sha256"],
        "governing_ir_nodes":sorted(n["node_id"] for n in ir["nodes"]),
        "review_status":"REVIEW_REQUIRED",
        "completeness":"UNKNOWN",
        "scope":"EXACT_REVIEWED_ROLE_GRAPH_CLAIMS_ONLY",
        "semantic_truth":"NOT_INDEPENDENTLY_ESTABLISHED",
    }


def verify_signed_role_review(
        *, source: str, candidate: str, source_facts: list[dict],
        candidate_facts: list[dict], ir: dict,
        signed_policy: dict, signed_review: dict,
        policy_keys: dict, reviewer_keys: dict,
        minimum_sequence: int, service: str,
        environment: str, as_of: str, nonce_accepted) -> dict:
    # Anchor the entire typed grammar directly to supplied document bytes.
    proposed = proposed_role_review(
        source=source,candidate=candidate,
        source_facts=source_facts,candidate_facts=candidate_facts,ir=ir)
    policy = verify_policy(
        signed_policy,policy_keys,service=service,environment=environment,
        as_of=as_of,minimum_sequence=minimum_sequence)
    if policy.get("ir") != ir:
        raise ValueError("Signed governing policy does not match role graph")
    if (not isinstance(signed_review,dict)
            or signed_review.get("key_id") == signed_policy.get("key_id")
            or signed_review.get("key_id") not in reviewer_keys):
        raise SignatureError("Separate authorized role reviewer required")
    body = verify(signed_review,reviewer_keys,schema=ATTEST_SCHEMA)
    expected = dict(proposed,review_status="REVIEWED_FINITE_ROLE_BINDINGS")
    observations = {"typed_role_graph_review":expected}
    if body.get("witnesses") != [] or body.get("observations") != observations:
        raise ValueError("Signed role graph review differs from exact document/inventory")
    if verify_attestation(
            signed_review,reviewer_keys,
            policy_signature=signed_policy["signature"],
            service=service,environment=environment,as_of=as_of,
            witnesses=[],observations=observations,
            nonce_accepted=nonce_accepted) is not True:
        raise SignatureError("Signed role review was not accepted")
    from hashlib import sha256
    audit = audit_typed_role_graph(
        source=source,candidate=candidate,
        source_facts=source_facts,candidate_facts=candidate_facts,
        source_sha256=sha256(source.encode()).hexdigest(),
        candidate_sha256=sha256(candidate.encode()).hexdigest(),
        source_inventory_sha256=digest(source_facts),
        candidate_inventory_sha256=digest(candidate_facts))
    receipt = {
        "schema":SCHEMA,
        "source_sha256":audit["source_sha256"],
        "candidate_sha256":audit["candidate_sha256"],
        "governing_ir_sha256":ir["ir_sha256"],
        "role_audit_fingerprint":audit["fingerprint"],
        "review_key_id":signed_review["key_id"],
        "signature_verified":True,
        "verdict":audit["verdict"],
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "semantic_completeness":"UNKNOWN",
        "semantic_truth":"NOT_INDEPENDENTLY_ESTABLISHED",
        "role_extraction":"EXTERNAL_REVIEWED_ANNOTATIONS_NOT_AUTOMATED",
    }
    receipt["fingerprint"]=digest(receipt)
    return receipt
