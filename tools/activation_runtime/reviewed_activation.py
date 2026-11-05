"""One reviewed finite workflow, reusing custody, release, review and interpreter gates."""
from .common import fingerprint,strict_json
from .contracts import validate
from .artifacts import verify_manifest
from .pipeline import activate_signed,encode
from .preservation import audit_output,bind_reviewed_contract
from .interpreter import execute_plan


def execute(raw,artifact,*,store,tenant,signed_manifest,release_keys,minimum_sequence,
            policy_ir,contract,signed_review,reviewer_keys,reviewer_subjects,author_public_key,
            nonce_store,as_of,allow_fallback):
    if type(allow_fallback) is not bool:raise ValueError("Explicit boolean fallback policy required")
    if not isinstance(contract,dict):raise ValueError("Preservation contract required")
    if contract.get("tenant")!=tenant:raise PermissionError("Contract tenant differs from authenticated tenant")
    validate("transform",artifact);validate("packspec",policy_ir)
    # Compile the total mapping first; partial mappings and invented payload fields refuse.
    expected=encode(raw,artifact["mapping"])
    if set(artifact["payload"])!=set(expected["payload"]):raise ValueError("Payload differs from total compiled mapping")
    source_hash=__import__("hashlib").sha256(raw).hexdigest();artifact_hash=fingerprint(artifact)
    if artifact["source_sha256"]!=source_hash:raise ValueError("Artifact/source identity mismatch")
    compatibility=verify_manifest(signed_manifest,release_keys,store=store,tenant=tenant,
        source_sha256=source_hash,artifact_sha256=artifact_hash,policy_ir_sha256=policy_ir["ir_sha256"],
        minimum_sequence=minimum_sequence,as_of=as_of)
    if store.get(source_hash)!=raw or strict_json(store.get(artifact_hash))!=artifact:
        raise ValueError("Source/artifact custody mismatch")
    candidate={field:artifact["payload"][target] for field,target in artifact["mapping"].items()}
    candidate_audit=audit_output(raw,candidate,contract,current_ir=policy_ir)
    # Run the canonical finite/unified gate before consuming review authority.
    canonical_result=activate_signed(raw,artifact,signed_manifest=signed_manifest,trusted_keys=release_keys,
        store=store,tenant=tenant,minimum_sequence=minimum_sequence,ir=policy_ir,witnesses=[],as_of=as_of)
    if candidate_audit["finite_constraint_result"]=="SAT" and canonical_result["finite_constraint_result"]!="SAT":
        raise ValueError("The canonical exact runtime cannot certify an approximation")
    binding=bind_reviewed_contract(raw,contract,policy_ir,signed_review=signed_review,
        reviewer_keys=reviewer_keys,reviewer_subjects=reviewer_subjects,author_public_key=author_public_key,
        as_of=as_of,nonce_store=nonce_store)
    plan=[{"op":"PRESERVE","fields":[row["field"] for row in contract["obligations"]]},
          {"op":"TRANSITION","mapping":artifact["mapping"]},
          {"op":"ACTIVATE","runtime":"finite-json/v1","payload":artifact["payload"]},{"op":"VERIFY"}]
    if candidate_audit["finite_constraint_result"]!="SAT" and allow_fallback:
        plan.append({"op":"FALLBACK","baseline":"original-source"})
    execution=execute_plan(raw,plan=plan,contract=contract,ir=policy_ir,max_steps=5)
    result={"schema":"qualityrag.reviewed-activation/v1","tenant":tenant,
        "source_sha256":source_hash,"artifact_sha256":artifact_hash,"contract_sha256":fingerprint(contract),
        "policy_ir_sha256":policy_ir["ir_sha256"],
        "action":"FALLBACK" if execution.get("fallback_used") else execution["action"],
        "finite_constraint_result":execution["finite_constraint_result"],"output":execution["output"],
        "execution":execution,"candidate_audit":candidate_audit,"canonical_candidate":canonical_result,
        "compatibility":compatibility,"preservation_review":binding,
        "fallback_authority":"SAME_SIGNED_SOURCE_AND_REVIEWED_CONTRACT" if allow_fallback else "DISABLED",
        "qualityrag_admission":"INCONCLUSIVE","can_generate":False,
        "evidence_boundary":"Authenticated finite execution; independent domain truth and production release are not established"}

    validate("reviewed-activation",result)
    return result
