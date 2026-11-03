"""Combine authenticated review and original APX semantic-text observations.

The exact signed review is revalidated with the canonical QualityRag policy,
Ed25519 attestation and durable nonce guard within this function. Never trust
a detached "VERIFIED" receipt as authority. Native results are still untrusted
observations until the host attests the original runtime and input custody.
"""
from __future__ import annotations

from rct_signed_span_review import verify_inventory_review
from store import digest

SCHEMA = "rct.dual-semantic-diagnostics/v2.2"


def combine_semantic_diagnostics(
        joined: dict, native: dict | None, *,
        ir: dict, signed_policy: dict, signed_review: dict,
        policy_keys: dict, reviewer_keys: dict,
        minimum_sequence: int, service: str, environment: str,
        as_of: str, nonce_accepted) -> dict:
    if not isinstance(joined, dict):
        raise ValueError("Source-bound research candidate required")
    # This is an actual signature/policy validation, not an assertion made
    # by an untrusted caller in a self-fingerprinted JSON receipt.
    reviewed=verify_inventory_review(
        joined=joined, ir=ir,
        signed_policy=signed_policy, signed_review=signed_review,
        policy_keys=policy_keys, reviewer_keys=reviewer_keys,
        minimum_sequence=minimum_sequence, service=service,
        environment=environment, as_of=as_of,
        nonce_accepted=nonce_accepted)
    audit=joined["source_span_audit"]
    blockers=["SIGNED_REVIEW_NOT_PROOF_OF_COMPLETE_MEANING",
              "SOURCE_AUTHORITY_UNVERIFIED",
              "NATIVE_RUNTIME_RESULT_NOT_INDEPENDENTLY_ATTESTED"]
    if native is None:
        native_status="UNAVAILABLE"
        native_verdict="INCONCLUSIVE"
        blockers.append("NATIVE_APX_SOURCE_COMPARATOR_NOT_EXECUTED")
    else:
        if (not isinstance(native, dict)
                or native.get("schema") != "qualityrag.native-semantic-transition/v1"
                or native.get("original_engine_schema") != "apx.semantic-text-transition/v0.1"
                or native.get("source_sha256") != audit.get("source_sha256")
                or native.get("candidate_sha256") != audit.get("candidate_sha256")
                or native.get("source_authority") != "UNVERIFIED_HEURISTIC"
                or native.get("semantic_completeness") != "UNKNOWN"
                or native.get("qualityrag_admission") != "INCONCLUSIVE"
                or native.get("can_generate") is not False
                or native.get("verdict") not in ("INCONCLUSIVE", "REFUSE")
                or not isinstance(native.get("observed_changes"), list)):
            raise ValueError("Native result cannot be bound to exact document versions")
        native_status="REPORTED_BOUNDED_LEXICAL_CHECK"
        native_verdict=native["verdict"]
    verdict=("REFUSE" if (joined.get("verdict") == "REFUSE"
                         or reviewed.get("verdict") == "REFUSE"
                         or native_verdict == "REFUSE") else "INCONCLUSIVE")
    result={
        "schema":SCHEMA,
        "joined_candidate_fingerprint":joined["fingerprint"],
        "verified_signed_review_fingerprint":reviewed["fingerprint"],
        "source_text_sha256":audit["source_sha256"],
        "candidate_text_sha256":audit["candidate_sha256"],
        "native_comparator_status":native_status,
        "native_verdict":native_verdict,
        "reviewed_span_verdict":reviewed["verdict"],
        "verdict":verdict,
        "semantic_completeness":"UNKNOWN",
        "source_authority":"UNVERIFIED",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "blockers":sorted(set(blockers)),
    }
    result["fingerprint"]=digest(result)
    return result
