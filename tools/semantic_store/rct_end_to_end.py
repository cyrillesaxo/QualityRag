"""End-to-end experimental RCT pipeline: induction -> purpose lens -> conservation
-> lossless reconstruction -> limited assurance diagnostics -> QualityRag candidate.

No model generation, ADMIT, source authority or FF-RCT claim is exposed.
"""
from __future__ import annotations

from rct_typed_grammar import induce_typed_rule, validate_typed_rule
from rct_purpose_lens import make_contract, compile_purpose_lens
from rct_conservation import audit_finite_conservation
from rct_reference_frame import encode_reference_frame, decode_reference_frame
from rct_assurance_candidates import (
    witness_cover_candidate, structural_drift_candidate)
from rct_source_custody import assess_source_custody
from store import digest

SCHEMA = "rct.end-to-end-experiment/v2"


def run_structural_pipeline(training: dict, training_labels: list[dict],
                            source: dict, labels: list[dict], grammar: dict,
                            *, purpose: str, lens_id: str,
                            required_predicates: list[str],
                            allowed_omission_predicates: list[str],
                            previous_source: dict | None = None) -> dict:
    """Construct, validate, reconstruct and audit one immutable lens candidate.

    Inconclusive induction does not yield a partial usable lens.
    """
    rule = induce_typed_rule(training, training_labels, grammar)
    if rule["status"] != "CANDIDATE":
        return {
            "schema": SCHEMA, "stage": "GRAMMAR_INDUCTION",
            "status": "UNKNOWN", "reason": rule.get("reason", "NO_CANDIDATE"),
            "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
            "source_sha256": digest(source), "training_result": rule,
        }
    assessment = validate_typed_rule(training, rule, source, labels, grammar)
    if assessment["finite_graph_verdict"] != "SAT":
        return {
            "schema": SCHEMA, "stage": "HELDOUT_VALIDATION",
            "status": assessment["status"], "qualityrag_admission": "INCONCLUSIVE",
            "can_generate": False, "source_sha256": digest(source),
            "training_result": rule, "validation": assessment,
        }
    contract = make_contract(
        source, labels, purpose=purpose, required_predicates=required_predicates,
        allowed_omission_predicates=allowed_omission_predicates)
    lens = compile_purpose_lens(
        source, labels, grammar=grammar, rule=rule, assessment=assessment,
        contract=contract, lens_id=lens_id)
    conservation = audit_finite_conservation(source, lens)
    frame = encode_reference_frame(source)
    restored = decode_reference_frame(frame)
    if digest(restored) != digest(source):
        raise AssertionError("Lossless source reconstruction invariant failed")
    witness_cover = witness_cover_candidate(lens)
    drift = (structural_drift_candidate(previous_source, source)
             if previous_source is not None else None)
    blockers = [
        "PACKSPEC_SOURCE_AUTHORITY_UNVERIFIED",
        "SEMANTIC_COMPLETENESS_UNPROVEN",
        "NATIVE_FF_RCT_NOT_IMPLEMENTED",
        "WBC_HCR_RCOC_CANONICAL_PARITY_NOT_ESTABLISHED",
    ]
    if conservation["finite_structural_verdict"] != "SAT":
        blockers.append("FINITE_RELATION_CONSERVATION_NOT_PROVEN")
    result = {
        "schema": SCHEMA,
        "stage": "RESEARCH_CANDIDATE",
        "status": "STRUCTURAL_CHECKS_PASS" if
                  conservation["finite_structural_verdict"] == "SAT"
                  else "STRUCTURAL_CHECKS_UNRESOLVED",
        "source_sha256": digest(source),
        "training_source_sha256": digest(training),
        "grammar_candidate": rule, "heldout_validation": assessment,
        "purpose_contract": contract, "purpose_lens": lens,
        "conservation": conservation,
        "reconstruction": {
            "frame": frame, "source_sha256": digest(restored),
            "exact_canonical_round_trip": True,
            "native_ff_rct": False,
        },
        "witness_cover": witness_cover,
        "structural_drift": drift,
        "blockers": blockers,
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
    }
    result["fingerprint"] = digest(result)
    return result


def attach_signed_governance(structural: dict, *,
                             reviewed_ir: dict, ir_binding: dict,
                             evidence_pack: dict, witness_mapping: dict,
                             signed_policy: dict, signed_observations: dict,
                             signed_custody: dict, policy_keys: dict,
                             attestor_keys: dict, custodian_keys: dict,
                             service: str, environment: str,
                             minimum_sequence: int, nonce_accepted,
                             witnesses: list[dict], observations: dict,
                             source_bytes: dict[str, bytes], as_of: str) -> dict:
    """Join the existing signed custody path with a structural lens candidate.

    The signed evidence must bind exactly to the newly constructed lens.
    """
    if not isinstance(structural, dict) or structural.get("stage") != "RESEARCH_CANDIDATE":
        raise ValueError("A complete experimental structural candidate is required")
    body = dict(structural)
    signature = body.pop("fingerprint", None)
    if (signature != digest(body)
            or structural.get("qualityrag_admission") != "INCONCLUSIVE"
            or structural.get("can_generate") is not False):
        raise ValueError("Untrusted structural candidate")
    if structural["conservation"]["finite_structural_verdict"] != "SAT":
        raise ValueError("Finite relation conservation has not been established")
    result = assess_source_custody(
        lens=structural["purpose_lens"],
        reviewed_ir=reviewed_ir, ir_binding=ir_binding,
        evidence_pack=evidence_pack, witness_mapping=witness_mapping,
        signed_policy=signed_policy, signed_observations=signed_observations,
        signed_custody=signed_custody, policy_keys=policy_keys,
        attestor_keys=attestor_keys, custodian_keys=custodian_keys,
        service=service, environment=environment,
        minimum_sequence=minimum_sequence, nonce_accepted=nonce_accepted,
        witnesses=witnesses, observations=observations,
        source_bytes=source_bytes, as_of=as_of)
    receipt = {
        "schema": "rct.end-to-end-signed-receipt/v2",
        "structural_receipt_sha256": signature,
        "source_custody_receipt_sha256": result["fingerprint"],
        "custody": result,
        "verdict": "REFUSE" if result["verdict"] == "REFUSE" else "INCONCLUSIVE",
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
        "blockers": sorted(set(structural["blockers"] + result["blockers"])),
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt


def attach_reviewed_signed_governance(
        structural: dict, *,
        reviewed_ir: dict, signed_review: dict, reviewer_keys: dict,
        signed_policy: dict, policy_keys: dict,
        service: str, environment: str, minimum_sequence: int,
        nonce_accepted, as_of: str, **custody_arguments) -> dict:
    """Strict combined research entry point: signed reviewer AND custody.

    Each independently signed attestation is one-shot and consumes a durable
    nonce. There is no automatic ADMIT or generation capability.
    """
    from rct_reviewed_obligations import verify_reviewed_mapping
    if not isinstance(structural, dict) or structural.get("stage") != "RESEARCH_CANDIDATE":
        raise ValueError("Full research pipeline requires a structural candidate")
    reviewed = verify_reviewed_mapping(
        lens=structural["purpose_lens"],
        ir=reviewed_ir, conservation=structural["conservation"],
        signed_policy=signed_policy, signed_review=signed_review,
        reviewer_keys=reviewer_keys, policy_keys=policy_keys,
        minimum_sequence=minimum_sequence,
        service=service, environment=environment,
        as_of=as_of, nonce_accepted=nonce_accepted)
    custody = attach_signed_governance(
        structural,
        reviewed_ir=reviewed_ir, signed_policy=signed_policy,
        policy_keys=policy_keys,
        service=service, environment=environment,
        minimum_sequence=minimum_sequence,
        nonce_accepted=nonce_accepted, as_of=as_of,
        **custody_arguments)
    result = {
        "schema": "rct.reviewed-end-to-end/v2",
        "structural_receipt_sha256": structural["fingerprint"],
        "reviewed_mapping": reviewed,
        "custody": custody["custody"],
        "signed_path_receipt_sha256": custody["fingerprint"],
        "verdict": "REFUSE" if custody["verdict"] == "REFUSE" else "INCONCLUSIVE",
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
        "blockers": sorted(set(custody["blockers"] + [
            "SEMANTIC_SUFFICIENCY_NOT_ESTABLISHED",
            "EXTERNAL_NATIVE_APX_PARITY_NOT_ATTESTED",
            "NATIVE_FF_RCT_NOT_IMPLEMENTED",
        ])),
    }
    result["fingerprint"] = digest(result)
    return result
