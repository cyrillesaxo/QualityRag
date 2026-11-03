"""Version-bound signed APX D15 *claims*, not authenticated deception proofs.

Reuses the canonical QualityRag signed-policy and signed-observation verifier.
A separate review key authenticates exactly which host-declared D15 statuses,
evidence-reference IDs and source/candidate versions were reviewed. No claimed
PASS is promoted to independent evidence, semantic ADMIT or FF-RCT compression.

The canonical original APX JS census runs separately. This module binds its
redacted receipt to a reviewed and signed inventory without reimplementing
its inference, normalization or precedence algorithm.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

_P = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_P) not in sys.path:
    sys.path.insert(0, str(_P))
from signed_bundles import ATTEST_SCHEMA, SignatureError, verify, verify_attestation, verify_policy
from store import digest

SCHEMA = "rct.signed-d15-evidence/v1"
FAMILIES = ("DW", "DD", "DS")
AXES = ("DEPTH", "BREADTH", "CHANNEL", "FRAME", "IMPLICATURE")
CELLS = tuple(f"{fam}_{axis}" for fam in FAMILIES for axis in AXES)
STATUSES = frozenset(("PASS", "FAIL", "INCONCLUSIVE", "UNTESTED"))
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _validated_native(native: dict) -> list[dict]:
    """Strictly cross-check native census self-consistency, not its origin."""
    if (not isinstance(native, dict)
            or native.get("schema") != "qualityrag.native-d15-diagnostics/v1"
            or native.get("original_engine_schema") != "apx.deception-census/v0.1"
            or native.get("qualityrag_admission") != "INCONCLUSIVE"
            or native.get("can_generate") is not False
            or native.get("compression_authorized") is not False
            or native.get("semantic_completeness") != "UNKNOWN"
            or native.get("verdict") not in ("REFUSE", "INCONCLUSIVE")
            or not isinstance(native.get("cells"), list)
            or len(native["cells"]) != 15):
        raise ValueError("Untrusted native D15 diagnostic contract")
    seen = set()
    rows = []
    for cell in native["cells"]:
        if (not isinstance(cell, dict) or set(cell) != {"id", "status", "evidence_refs"}
                or cell.get("id") not in CELLS or cell["id"] in seen
                or cell.get("status") not in STATUSES
                or not isinstance(cell.get("evidence_refs"), list)
                or len(cell["evidence_refs"]) > 200
                or any(not isinstance(x, str) or not x or len(x) > 128
                       for x in cell["evidence_refs"])
                or len(set(cell["evidence_refs"])) != len(cell["evidence_refs"])):
            raise ValueError("Malformed or duplicate D15 cell")
        if cell["status"] in ("PASS", "FAIL") and not cell["evidence_refs"]:
            raise ValueError("Claimed D15 PASS/FAIL requires explicit evidence IDs")
        seen.add(cell["id"])
        rows.append({"id":cell["id"],"status":cell["status"],
                     "evidence_refs":sorted(cell["evidence_refs"])})
    if seen != set(CELLS):
        raise ValueError("Incomplete canonical D15 census")
    index = {x["id"]:x for x in rows}
    rows = [index[code] for code in CELLS]
    counts = {state: [x["id"] for x in rows if x["status"] == state]
              for state in STATUSES}
    for state, field in (("PASS","passed_cells"),("FAIL","failed_cells"),
                         ("INCONCLUSIVE","inconclusive_cells"),("UNTESTED","untested_cells")):
        if native.get(field) != counts[state]:
            raise ValueError("D15 status lists do not match canonical inventory")
    expected = "REFUSE" if counts["FAIL"] else "INCONCLUSIVE"
    if native["verdict"] != expected:
        raise ValueError("D15 verdict does not match cell failures")
    return rows


def proposed_d15_review(*, native: dict, source_sha256: str,
                         candidate_sha256: str, reviewed_ir: dict,
                         evidence_registry: dict[str, str]) -> dict:
    """Make a reviewer draft with complete explicit evidence-record hashes.

    The registry maps each cited evidence reference to its verified-by-host
    record SHA-256. These are labels provided by the host, NOT authenticated
    provenance unless a separate custody/attestation flow checked them.
    """
    cells = _validated_native(native)
    if (not isinstance(source_sha256,str) or not _SHA.fullmatch(source_sha256)
            or not isinstance(candidate_sha256,str) or not _SHA.fullmatch(candidate_sha256)
            or not isinstance(evidence_registry,dict)
            or len(evidence_registry)>2000
            or any(not isinstance(k,str) or not k or len(k)>128
                   or not isinstance(v,str) or not _SHA.fullmatch(v)
                   for k,v in evidence_registry.items())):
        raise ValueError("Source digests and bounded evidence registry required")
    cited = {ref for row in cells for ref in row["evidence_refs"]}
    if cited != set(evidence_registry):
        raise ValueError("Every cited evidence ID must have one exact content digest")
    from typed_ir import _fingerprint
    if (not isinstance(reviewed_ir,dict)
            or reviewed_ir.get("ir_sha256") != _fingerprint({
               "source_sha256":reviewed_ir.get("source",{}).get("sha256"),
               "nodes":reviewed_ir.get("nodes")})
            or not isinstance(reviewed_ir.get("nodes"),list)
            or not reviewed_ir["nodes"]):
        raise ValueError("Invalid reviewed PackSpec IR")
    return {
        "schema":SCHEMA,
        "source_sha256":source_sha256,
        "candidate_sha256":candidate_sha256,
        "packspec_source_sha256":reviewed_ir["source"]["sha256"],
        "packspec_ir_sha256":reviewed_ir["ir_sha256"],
        "reviewed_nodes":sorted(n["node_id"] for n in reviewed_ir["nodes"]),
        "canonical_cells":cells,
        "evidence_record_sha256":{ref:evidence_registry[ref] for ref in sorted(cited)},
        "review_status":"REVIEW_REQUIRED",
        "source_authority":"NOT_ESTABLISHED",
        "deception_probe_execution":"NOT_ATTESTED",
        "semantic_completeness":"UNKNOWN",
        "compression_authorized":False,
    }


def verify_d15_review(*, native: dict, source_sha256: str,
                      candidate_sha256: str, reviewed_ir: dict,
                      evidence_registry: dict[str,str], signed_policy: dict,
                      signed_review: dict, policy_keys: dict, reviewer_keys: dict,
                      minimum_sequence: int, service: str, environment: str,
                      as_of: str, nonce_accepted) -> dict:
    draft = proposed_d15_review(
        native=native,source_sha256=source_sha256,
        candidate_sha256=candidate_sha256,reviewed_ir=reviewed_ir,
        evidence_registry=evidence_registry)
    p = verify_policy(signed_policy,policy_keys,service=service,
                      environment=environment,as_of=as_of,
                      minimum_sequence=minimum_sequence)
    if p.get("ir") != reviewed_ir:
        raise ValueError("Signed governing PackSpec mismatch")
    if (not isinstance(signed_review,dict)
            or signed_review.get("key_id") == signed_policy.get("key_id")
            or signed_review.get("key_id") not in reviewer_keys):
        raise SignatureError("Dedicated trusted D15 reviewer key required")
    body = verify(signed_review,reviewer_keys,schema=ATTEST_SCHEMA)
    expected = dict(draft,review_status="REVIEWED_FINITE_D15_CLAIMS")
    observations = {"d15_review":expected}
    if body.get("witnesses") != [] or body.get("observations") != observations:
        raise ValueError("Signed D15 review differs from source, cells or evidence registry")
    if verify_attestation(
            signed_review,reviewer_keys,
            policy_signature=signed_policy["signature"],
            service=service,environment=environment,as_of=as_of,
            witnesses=[],observations=observations,
            nonce_accepted=nonce_accepted) is not True:
        raise SignatureError("Signed D15 evidence review rejected")
    failed = [x["id"] for x in draft["canonical_cells"] if x["status"]=="FAIL"]
    untested = [x["id"] for x in draft["canonical_cells"] if x["status"]=="UNTESTED"]
    inconclusive = [x["id"] for x in draft["canonical_cells"]
                    if x["status"]=="INCONCLUSIVE"]
    result = {
        "schema":SCHEMA,
        "source_sha256":source_sha256,
        "candidate_sha256":candidate_sha256,
        "packspec_ir_sha256":reviewed_ir["ir_sha256"],
        "reviewer_key_id":signed_review["key_id"],
        "native_d15_receipt_sha256":digest(native),
        "reviewed_claims_sha256":digest(expected),
        "claimed_pass_count":sum(x["status"]=="PASS" for x in draft["canonical_cells"]),
        "failed_cells":failed,
        "untested_cells":untested,
        "inconclusive_cells":inconclusive,
        "verdict":"REFUSE" if failed else "INCONCLUSIVE",
        "source_authority":"NOT_ESTABLISHED",
        "independent_evidence_custody":"NOT_ESTABLISHED",
        "deception_probe_execution":"NOT_ATTESTED",
        "semantic_completeness":"UNKNOWN",
        "compression_authorized":False,
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
    }
    result["fingerprint"]=digest(result)
    return result
