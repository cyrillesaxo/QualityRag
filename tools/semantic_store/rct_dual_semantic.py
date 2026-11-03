"""Combine signed inventory and canonical APX semantic text observations.

Diagnostic-only fusion: neither a self-reported native response nor a
reviewer signature establishes completeness. Any observed REFUSE dominates;
absence/mismatch of the native engine is UNKNOWN, never a silent pass.
"""
from __future__ import annotations

from store import digest

SCHEMA = "rct.dual-semantic-diagnostics/v2.2"


def combine_semantic_diagnostics(joined: dict, reviewed: dict,
                                 native: dict | None) -> dict:
    if not isinstance(joined, dict) or not isinstance(reviewed, dict):
        raise ValueError("Joined structural/span receipt and signed review receipt required")
    j, r = dict(joined), dict(reviewed)
    jf, rf = j.pop("fingerprint", None), r.pop("fingerprint", None)
    if (jf != digest(j) or rf != digest(r)
            or joined.get("schema") != "rct.source-span-joined-candidate/v2.1"
            or reviewed.get("schema") != "rct.signed-source-span-inventory/v2.2"
            or reviewed.get("review_signature") != "VERIFIED"
            or reviewed.get("joined_candidate_fingerprint") != jf
            or reviewed.get("span_audit_fingerprint") !=
               joined.get("source_span_audit", {}).get("fingerprint")
            or joined.get("can_generate") is not False
            or reviewed.get("can_generate") is not False
            or joined.get("qualityrag_admission") != "INCONCLUSIVE"
            or reviewed.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Untrusted or mismatched signed source-span review")
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
        "joined_candidate_fingerprint":jf,
        "signed_review_fingerprint":rf,
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
