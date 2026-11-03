"""Signed, explicitly reviewed projection onto canonical APX G1-G12 codes.

Never infers a G code from a source lexical-kind label. Reviewers classify
which source-span distinctions touch which canonical coordinates, and must
declare all twelve coordinates (including as not observed). Review signatures
bind this exact map to governing ConstraintIR, source/candidate SHA and signed
span-review identity. Signed absence is NOT proof of semantic non-applicability.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

_P = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_P) not in sys.path:
    sys.path.insert(0,str(_P))

from signed_bundles import (
    ATTEST_SCHEMA, SignatureError, verify, verify_attestation, verify_policy)
from rct_signed_span_review import (
    proposed_inventory_review, verify_inventory_review)
from store import digest

SCHEMA = "rct.reviewed-g-coordinate-map/v2.3"
CODES = tuple(f"G{i}" for i in range(1,13))


def propose_g_mapping(joined: dict, ir: dict, mapping: list[dict]) -> dict:
    """Inert draft; a separately configured reviewer must inspect and sign."""
    source_review = proposed_inventory_review(joined,ir)
    if not isinstance(mapping,list) or len(mapping)!=len(CODES):
        raise ValueError("Every canonical G1-G12 coordinate needs a declaration")
    by_code: dict[str,dict] = {}
    reviewed_ids = {x["id"] for x in joined["source_span_audit"]["findings"]}
    mapped_ids: set[str] = set()
    for entry in mapping:
        if (not isinstance(entry,dict) or set(entry)!={"code","observed","obligation_ids"}
                or entry.get("code") not in CODES):
            raise ValueError("Invalid canonical G coordinate declaration")
        code=entry["code"]
        if code in by_code:
            raise ValueError("Duplicate semantic coordinate")
        obs=entry["observed"]
        ids=entry["obligation_ids"]
        if (type(obs) is not bool or not isinstance(ids,list)
                or any(not isinstance(x,str) or x not in reviewed_ids for x in ids)
                or len(ids)!=len(set(ids))
                or (not obs and bool(ids))
                or (obs and not ids)):
            raise ValueError("G coordinate mapping must use explicit reviewed obligations")
        by_code[code]={"code":code,"observed":obs,"obligation_ids":sorted(ids)}
        mapped_ids.update(ids)
    if set(by_code)!=set(CODES) or mapped_ids!=reviewed_ids:
        raise ValueError("Every reviewed distinction must map to a canonical G code")
    return {
        "schema":SCHEMA,
        "joined_candidate_fingerprint":joined["fingerprint"],
        "span_inventory_sha256":source_review["obligation_inventory_sha256"],
        "source_text_sha256":source_review["source_text_sha256"],
        "candidate_text_sha256":source_review["candidate_text_sha256"],
        "governing_ir_sha256":ir["ir_sha256"],
        "governing_source_sha256":ir["source"]["sha256"],
        "coordinates":[by_code[code] for code in CODES],
        "review_status":"REVIEW_REQUIRED",
        "semantic_completeness":"UNKNOWN",
        "unobserved_coordinates":"NOT_PROVEN_NOT_APPLICABLE",
        "independent_authority":"NOT_ESTABLISHED",
    }


def verify_reviewed_g_mapping(*, joined: dict, ir: dict, mapping: list[dict],
                              signed_policy: dict, signed_span_review: dict,
                              signed_g_review: dict, policy_keys: dict,
                              span_reviewer_keys: dict, g_reviewer_keys: dict,
                              minimum_sequence: int, service: str,
                              environment: str, as_of: str,
                              nonce_accepted) -> dict[str,Any]:
    """Run canonical cryptographic checks; emit bounded G observation snapshot.

    No native RCOC delta can be inferred: all measured metric fields remain
    null, even for an observed source-span contradiction.
    """
    draft=propose_g_mapping(joined,ir,mapping)
    signed=verify_policy(
        signed_policy,policy_keys,service=service,
        environment=environment,as_of=as_of,
        minimum_sequence=minimum_sequence)
    if signed.get("ir")!=ir:
        raise ValueError("G mapping governing policy differs from reviewed IR")
    if (not isinstance(signed_span_review,dict)
            or not isinstance(signed_g_review,dict)
            or signed_g_review.get("key_id") in {
                signed_policy.get("key_id"),signed_span_review.get("key_id")}
            or signed_g_review.get("key_id") not in g_reviewer_keys):
        raise SignatureError("Dedicated trusted G reviewer key required")
    payload=verify(signed_g_review,g_reviewer_keys,schema=ATTEST_SCHEMA)
    approved=dict(draft,review_status="REVIEWED_FINITE_COORDINATE_MAP")
    if (payload.get("witnesses")!=[]
            or payload.get("observations")!={"rct_reviewed_g_map":approved}):
        raise ValueError("Signed G coordinate inventory differs from reviewed source")
    # All shape, content and signatures are verified before spending the
    # source-span review nonce. Both attestations still have separate durable
    # nonces and are not an atomic two-phase transaction.
    span_review=verify_inventory_review(
        joined=joined,ir=ir,signed_policy=signed_policy,
        signed_review=signed_span_review,policy_keys=policy_keys,
        reviewer_keys=span_reviewer_keys,
        minimum_sequence=minimum_sequence,service=service,
        environment=environment,as_of=as_of,nonce_accepted=nonce_accepted)
    if verify_attestation(
        signed_g_review,g_reviewer_keys,
        policy_signature=signed_policy["signature"],
        service=service,environment=environment,as_of=as_of,
        witnesses=[],observations={"rct_reviewed_g_map":approved},
        nonce_accepted=nonce_accepted) is not True:
        raise SignatureError("G mapping signature/replay rejected")
    findings={x["id"]:x for x in joined["source_span_audit"]["findings"]}
    coordinates=[]
    for entry in approved["coordinates"]:
        statuses=[findings[x]["status"] for x in entry["obligation_ids"]]
        if any(s in ("MISSING_REQUIRED","CONTRADICTED") for s in statuses):
            observed_status="OBSERVED_VIOLATION"
        elif any(s in ("UNMEASURED","DECLARED_OPTIONAL_OMISSION") for s in statuses):
            observed_status="UNRESOLVED"
        elif statuses:
            observed_status="DECLARED_PRESERVATION"
        else:
            observed_status="UNOBSERVED"
        coordinates.append({
            "code":entry["code"],
            "reviewed_obligation_ids":entry["obligation_ids"],
            "observed_status":observed_status,
            "source_observed":entry["observed"],
            "semantic_adequacy":"UNKNOWN",
        })
    # The canonical APX RCOC snapshot expects measurements deltaRef/pHat
    # that these finite text witnesses cannot provide. Set null explicitly.
    snapshot={
        "schema":"apx.semantic-assurance-snapshot/v0.1",
        "revision":joined["source_span_audit"]["candidate_sha256"],
        "coordinates":[{"id":c["code"],
                        "applicable":c["source_observed"],
                        "deltaRef":None}
                       for c in coordinates],
    }
    refused=(span_review["verdict"]=="REFUSE"
             or any(c["observed_status"]=="OBSERVED_VIOLATION" for c in coordinates))
    receipt={
        "schema":SCHEMA,
        "joined_candidate_fingerprint":joined["fingerprint"],
        "verified_span_review_sha256":span_review["fingerprint"],
        "reviewer_key_id":signed_g_review["key_id"],
        "governing_ir_sha256":ir["ir_sha256"],
        "coordinates":coordinates,
        "canonical_rcoc_snapshot":snapshot,
        "verdict":"REFUSE" if refused else "INCONCLUSIVE",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "semantic_completeness":"UNKNOWN",
        "source_authority":"NOT_ESTABLISHED",
        "boundary":"Signed coordinate assignment, not verified semantic classification or G displacement measurement",
    }
    receipt["fingerprint"]=digest(receipt)
    return receipt
