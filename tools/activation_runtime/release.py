"""Independent signed release gate; software CI cannot authorize research claims."""
from .authority import verify_review
from .common import fingerprint,HEX,identity


REQUIRED=("security_review","privacy_review","licensing_review","supported_devices",
          "signed_artifacts","rollback_test","independent_fidelity_review","telemetry")


def readiness(evidence,*,critical_field_failures,total_cost_comparison):
    if not isinstance(evidence,dict) or set(evidence)!=set(REQUIRED):raise ValueError("Complete release evidence inventory required")
    if type(critical_field_failures) is not int or critical_field_failures<0:raise ValueError("Measured critical-field count required")
    missing=[k for k,v in evidence.items() if not isinstance(v,dict) or set(v)!={"receipt_sha256","status"}
             or v["status"]!="INDEPENDENTLY_VERIFIED" or not isinstance(v["receipt_sha256"],str) or not HEX.fullmatch(v["receipt_sha256"])]
    blockers=missing+(["CRITICAL_FIELD_LOSS"] if critical_field_failures else [])
    if total_cost_comparison not in {"MEASURED_ADVANTAGE","MEASURED_NO_CROSSOVER","UNKNOWN"}:
        raise ValueError("Explicit economic outcome required")
    if total_cost_comparison=="UNKNOWN":blockers.append("UNKNOWN_TOTAL_COST")
    return {"decision":"BLOCK" if blockers else "REQUIRES_SIGNED_INDEPENDENT_RELEASE_APPROVAL",
            "blockers":blockers,"economic_outcome":total_cost_comparison,
            "can_release":False,"evidence_sha256":fingerprint(evidence)}


def approval_context(evidence,*,critical_field_failures,total_cost_comparison,context,tenant,minimum_sequence):
    """Exact signed scope for one research-pilot candidate, never production admission."""
    identity(tenant)
    hashes={"source_sha256","artifact_sha256","policy_ir_sha256","grammar_sha256","model_sha256","decoder_sha256"}
    if not isinstance(context,dict) or set(context)!=hashes|{"run_id","sequence","service","environment"}:
        raise ValueError("Complete pinned pilot manifest required")
    for field in hashes:
        if not isinstance(context[field],str) or not HEX.fullmatch(context[field]):raise ValueError("Pinned pilot hashes required")
    for field in ("run_id","service","environment"):identity(context[field])
    if type(minimum_sequence) is not int or minimum_sequence<1 or type(context["sequence"]) is not int or context["sequence"]<minimum_sequence:
        raise ValueError("Pilot release must meet the host version floor")
    gate=readiness(evidence,critical_field_failures=critical_field_failures,total_cost_comparison=total_cost_comparison)
    if gate["blockers"]:raise ValueError("Blocked readiness cannot request release approval")
    return {"schema":"qualityrag.pilot-release-approval/v1","purpose":"AUTHORIZE_RESEARCH_PILOT",
            "tenant":tenant,"manifest":dict(context),"release_evidence_sha256":gate["evidence_sha256"],
            "critical_field_failures":critical_field_failures,"economic_outcome":total_cost_comparison,
            "minimum_sequence":minimum_sequence}


def authorize_release(evidence,*,critical_field_failures,total_cost_comparison,context,
                      signed_review,reviewer_keys,reviewer_subjects,author_public_key,as_of,nonce_store,tenant,minimum_sequence):
    gate=readiness(evidence,critical_field_failures=critical_field_failures,total_cost_comparison=total_cost_comparison)
    if gate["blockers"]:return gate
    if not isinstance(reviewer_subjects,dict):raise PermissionError("Host-assigned release reviewer required")
    bound=approval_context(evidence,critical_field_failures=critical_field_failures,
        total_cost_comparison=total_cost_comparison,context=context,tenant=tenant,minimum_sequence=minimum_sequence)
    review=verify_review(signed_review,reviewer_keys,context=bound,author_public_key=author_public_key,
                        as_of=as_of,nonce_store=nonce_store,tenant=tenant,reviewer_subjects=reviewer_subjects)
    return {**gate,"decision":"HOST_AUTHORIZED_RESEARCH_PILOT","can_release":True,"review":review,
            "release_scope":"RESEARCH_PILOT_ONLY","can_release_production":False,"can_generate":False,
            "approved_context":bound,"approved_context_sha256":fingerprint(bound),
            "boundary":"Configured independent reviewer authorization, not an automatic scientific truth claim"}
