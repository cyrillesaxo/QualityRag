"""RCT v1.7: evidence-obligation bridge using canonical Python WitnessGraph.

Maps every required predicate and omitted optional predicate to a declared
evidence requirement. It reuses qualityrag.compiler.evaluate_compiled for
origin-based gaps, scope, authority, freshness and contradictions. The result
is never authenticated semantic admission or safe-omission authorization.
"""
from __future__ import annotations

from pathlib import Path
import sys

_SDK = Path(__file__).resolve().parents[2] / "sdk" / "python"
if str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from qualityrag.compiler import compile_pack, evaluate_compiled
from rct_grammar import _ident
from store import digest

SCHEMA = "rct.witness-obligation-mapping/v1.7"
RECEIPT = "rct.witness-coverage/v1.7"


def make_mapping(lens: dict, *, pack: dict, predicate_requirements: dict[str, str]) -> dict:
    if not isinstance(lens, dict) or not isinstance(pack, dict):
        raise ValueError("Lens and evidence PackSpec required")
    data = dict(lens)
    lf = data.pop("fingerprint", None)
    if (lf != digest(data) or lens.get("qualityrag_admission") != "INCONCLUSIVE"
            or not isinstance(lens.get("source_sha256"), str)):
        raise ValueError("Invalid lens candidate")
    obligations = compile_pack(pack)  # Canonical compiler validates requirement identity.
    known = {x.requirement_id for x in obligations}
    required, optional = lens.get("required"), lens.get("permitted_omissions")
    if (not isinstance(required, list) or not isinstance(optional, list)
            or not isinstance(predicate_requirements, dict)
            or not set(required + optional) == set(predicate_requirements)
            or any(not _ident(p) or not _ident(v) or v not in known
                   for p, v in predicate_requirements.items())):
        raise ValueError("Each declared distinction needs a known evidence obligation")
    # A single evidence requirement cannot stand in for two distinct claims.
    if len(set(predicate_requirements.values())) != len(predicate_requirements):
        raise ValueError("Distinctions cannot silently share evidence obligations")
    result = {
        "schema": SCHEMA,
        "lens_fingerprint": lf,
        "lens_source_sha256": lens["source_sha256"],
        "pack_sha256": digest(pack),
        "predicate_requirements": dict(sorted(predicate_requirements.items())),
        "required_predicates": sorted(required),
        "optional_predicates": sorted(optional),
        "authentication": "UNVERIFIED_REVIEW_MAPPING",
        "omission_authorization": "NOT_ESTABLISHED",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    result["fingerprint"] = digest(result)
    return result


def evaluate_witness_coverage(lens: dict, pack: dict, mapping: dict,
                              evidence: list[dict], *, as_of: str) -> dict:
    if not isinstance(lens, dict) or not isinstance(mapping, dict):
        raise ValueError("Lens/mapping required")
    l, m = dict(lens), dict(mapping)
    lf, mf = l.pop("fingerprint", None), m.pop("fingerprint", None)
    if (lf != digest(l) or mf != digest(m)
            or mapping.get("schema") != SCHEMA
            or mapping.get("lens_fingerprint") != lf
            or mapping.get("lens_source_sha256") != lens.get("source_sha256")
            or mapping.get("pack_sha256") != digest(pack)
            or mapping.get("required_predicates") != sorted(lens.get("required", []))
            or mapping.get("optional_predicates") != sorted(lens.get("permitted_omissions", []))
            or mapping.get("authentication") != "UNVERIFIED_REVIEW_MAPPING"
            or mapping.get("omission_authorization") != "NOT_ESTABLISHED"
            or mapping.get("qualityrag_admission") != "INCONCLUSIVE"
            or lens.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Stale, altered, or untrusted evidence mapping")
    # Re-check all covered distinctions and existence/uniqueness of requirements.
    obligations = compile_pack(pack)
    known = {o.requirement_id for o in obligations}
    mapping_values = mapping.get("predicate_requirements")
    declared = set(lens["required"] + lens["permitted_omissions"])
    if (not isinstance(mapping_values, dict) or set(mapping_values) != declared
            or len(set(mapping_values.values())) != len(mapping_values)
            or not set(mapping_values.values()) <= known):
        raise ValueError("Incomplete evidence mapping")
    evidence_result = evaluate_compiled(pack, evidence, as_of=as_of)
    findings = {f["requirement_id"]: f for f in evidence_result["findings"]}
    status = {}
    for predicate, rid in sorted(mapping_values.items()):
        finding = findings[rid]
        status[predicate] = {
            "requirement_id": rid,
            "metadata_verdict": finding["verdict"],
            "declared_independent_origin_count": finding["independent_sources"],
            "missing_origin_count": finding["missing_sources"],
            "reasons": finding["reasons"],
            "governed_sufficiency": "UNKNOWN",
        }
    blockers = ["ORIGIN_INDEPENDENCE_NOT_AUTHENTICATED",
                "PREDICATE_TO_SEMANTIC_OBLIGATION_MAPPING_UNVERIFIED",
                "OMISSION_SAFETY_NOT_ESTABLISHED",
                "PACKSPEC_COMPLETENESS_NOT_ESTABLISHED"]
    if any(x["verdict"] == "REFUSE" for x in findings.values()):
        verdict = "REFUSE"
        blockers.append("EVIDENCE_CONTRADICTION")
    else:
        verdict = "INCONCLUSIVE"
        if any(x["verdict"] != "ADMIT" for x in findings.values()):
            blockers.append("EVIDENCE_GAPS_OR_UNRESOLVED_REQUIREMENTS")
    receipt = {
        "schema": RECEIPT,
        "lens_fingerprint": lf,
        "mapping_sha256": mf,
        "pack_sha256": digest(pack),
        "as_of": as_of,
        "canonical_evidence_result": evidence_result,
        "witness_graph": evidence_result["witness_graph"],
        "wgap": evidence_result["wgap"],
        "distinction_coverage": status,
        "verdict": verdict,
        "can_generate": False,
        "omission_authorization": "NOT_ESTABLISHED",
        "qualityrag_admission": "INCONCLUSIVE",
        "blockers": blockers,
        "limits": "Origin labels do not demonstrate actual independence or source authority",
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt
