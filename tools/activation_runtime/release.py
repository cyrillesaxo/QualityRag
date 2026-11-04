"""Independent signed release gate; software CI cannot authorize research claims."""
from .authority import verify_review
from .common import fingerprint


REQUIRED=("security_review","privacy_review","licensing_review","supported_devices",
          "signed_artifacts","rollback_test","independent_fidelity_review","telemetry")


def readiness(evidence,*,critical_field_failures,total_cost_comparison):
    if not isinstance(evidence,dict) or set(evidence)!=set(REQUIRED):raise ValueError("Complete release evidence inventory required")
    if type(critical_field_failures) is not int or critical_field_failures<0:raise ValueError("Measured critical-field count required")
    missing=[k for k,v in evidence.items() if not isinstance(v,dict) or set(v)!={"receipt_sha256","status"} or v["status"]!="INDEPENDENTLY_VERIFIED" or len(v["receipt_sha256"])!=64]
    blockers=missing+(["CRITICAL_FIELD_LOSS"] if critical_field_failures else [])
    if total_cost_comparison not in {"MEASURED_ADVANTAGE","MEASURED_NO_CROSSOVER","UNKNOWN"}:
        raise ValueError("Explicit economic outcome required")
    if total_cost_comparison=="UNKNOWN":blockers.append("UNKNOWN_TOTAL_COST")
    return {"decision":"BLOCK" if blockers else "REQUIRES_SIGNED_INDEPENDENT_RELEASE_APPROVAL",
            "blockers":blockers,"economic_outcome":total_cost_comparison,
            "can_release":False,"evidence_sha256":fingerprint(evidence)}


def authorize_release(evidence,*,critical_field_failures,total_cost_comparison,context,
                      signed_review,reviewer_keys,author_public_key,as_of,nonce_store,tenant):
    gate=readiness(evidence,critical_field_failures=critical_field_failures,total_cost_comparison=total_cost_comparison)
    if gate["blockers"]:return gate
    bound={**context,"release_evidence_sha256":gate["evidence_sha256"],"economic_outcome":total_cost_comparison}
    review=verify_review(signed_review,reviewer_keys,context=bound,author_public_key=author_public_key,
                        as_of=as_of,nonce_store=nonce_store,tenant=tenant)
    return {**gate,"decision":"HOST_AUTHORIZED_RESEARCH_PILOT","can_release":True,"review":review,
            "boundary":"Configured independent reviewer authorization, not an automatic scientific truth claim"}
