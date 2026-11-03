"""RCT v1.9 custody extension: verified bytes and separately signed root manifest.

Uses the canonical QualityRag Ed25519 observation attestation verifier, with
a *separate* host-managed custodian trust map and durable nonce ledger.
Content hash equality proves identical bytes; differing hashes cannot prove
independence, truthful content, or semantic adequacy.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import sys

_PACKSPEC = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_PACKSPEC) not in sys.path:
    sys.path.insert(0, str(_PACKSPEC))

from signed_bundles import verify_attestation, SignatureError
from rct_signed_lineage import _lineage, assess_signed_lineage
from store import digest

SCHEMA = "rct.source-custody/v1.9"
_HEX = re.compile(r"^[0-9a-f]{64}$")


def _verify_custody_manifest(witnesses: list[dict], records: list[dict],
                             source_bytes: dict[str, bytes]) -> dict:
    """Compare the declared primary roots to actual supplied bytes.

    No on-disk reading, network retrieval, or implicit source discovery.
    A caller must provide all exact raw source bytes for every root.
    """
    lineage = _lineage(witnesses)
    roots = {row["origin"]: row for row in witnesses
             if not row["derives_from"]}
    if not isinstance(records, list) or not records or len(records) > 200:
        raise ValueError("Bounded custody manifest required")
    if not isinstance(source_bytes, dict) or set(source_bytes) != set(roots):
        raise ValueError("Every primary root must supply its exact source bytes")
    manifest = {}
    for entry in records:
        if not isinstance(entry, dict) or set(entry) != {
                "root_id", "source_ref", "content_sha256", "content_length"}:
            raise ValueError("Invalid root custody record")
        root = entry["root_id"]
        if not isinstance(root, str) or not root or root in manifest or root not in roots:
            raise ValueError("Missing or duplicate declared root identity")
        raw = source_bytes[root]
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= 2_000_000:
            raise ValueError("Invalid source byte payload")
        declared = entry["content_sha256"]
        if (not isinstance(declared, str) or not _HEX.fullmatch(declared)
                or type(entry["content_length"]) is not int
                or entry["content_length"] != len(raw)
                or declared != sha256(raw).hexdigest()
                or entry["source_ref"] != roots[root]["source_ref"]):
            raise ValueError("Source substitution or custody digest mismatch")
        manifest[root] = entry
    if set(manifest) != set(roots):
        raise ValueError("Unattested primary root")
    # Root aliases pointing to identical bytes are conservatively collapsed.
    hash_to_roots = {}
    for root, item in manifest.items():
        hash_to_roots.setdefault(item["content_sha256"], []).append(root)
    aliases = [sorted(group) for group in hash_to_roots.values() if len(group) > 1]
    return {
        "schema": SCHEMA,
        "verified_root_bytes": len(manifest),
        "root_content_sha256": {root: manifest[root]["content_sha256"]
                                for root in sorted(manifest)},
        "identical_content_root_groups": sorted(aliases),
        "declared_ancestry": lineage["witness_roots"],
        "custody_assurance": "SIGNED_HASH_MATCHES_SUPPLIED_BYTES_ONLY",
        "independent_primary_sources": "UNKNOWN",
    }


def assess_source_custody(*, lens: dict, reviewed_ir: dict, ir_binding: dict,
                          evidence_pack: dict, witness_mapping: dict,
                          signed_policy: dict, signed_observations: dict,
                          signed_custody: dict, policy_keys: dict,
                          attestor_keys: dict, custodian_keys: dict,
                          service: str, environment: str, minimum_sequence: int,
                          nonce_accepted, witnesses: list[dict], observations: dict,
                          source_bytes: dict[str, bytes], as_of: str) -> dict:
    """Require custody and witness signatures; return diagnostic only.

    A non-atomic two-attestation flow consumes custody nonce first.
    If later evaluation fails, the spent custody nonce cannot be reused.
    Hosts must supply distinct trust key registries and persistent replay guard.
    """
    if not isinstance(signed_custody, dict):
        raise ValueError("Signed custody envelope required")
    if (not isinstance(attestor_keys, dict) or not isinstance(custodian_keys, dict)
            or set(attestor_keys) & set(custodian_keys)):
        raise ValueError("Custody and evidence attestor key IDs must be separate")
    if signed_custody.get("key_id") not in custodian_keys:
        raise SignatureError("Untrusted custodian")
    if not isinstance(signed_policy, dict) or not isinstance(observations, dict):
        raise ValueError("Signed policy and observations required")
    custody_records = signed_custody.get("payload", {}).get("observations", {}).get("custody_roots")
    if not isinstance(custody_records, list):
        raise ValueError("Missing signed custody roots")
    # Verify signed envelope against the exact source manifest, policy and nonce.
    # Crucially no ability to substitute a signed unrelated source list.
    verified = verify_attestation(
        signed_custody, custodian_keys,
        policy_signature=signed_policy["signature"],
        service=service, environment=environment, as_of=as_of,
        witnesses=[], observations={"custody_roots": custody_records},
        nonce_accepted=nonce_accepted)
    if verified is not True:
        raise SignatureError("Custody attestation rejected")
    custody = _verify_custody_manifest(witnesses, custody_records, source_bytes)
    prior = assess_signed_lineage(
        lens=lens, reviewed_ir=reviewed_ir, ir_binding=ir_binding,
        evidence_pack=evidence_pack, witness_mapping=witness_mapping,
        signed_policy=signed_policy, signed_observations=signed_observations,
        policy_keys=policy_keys, attestor_keys=attestor_keys,
        service=service, environment=environment,
        minimum_sequence=minimum_sequence, nonce_accepted=nonce_accepted,
        witnesses=witnesses, observations=observations, as_of=as_of)
    # Independent source assertions still UNKNOWN even if all hashes differ.
    result = {
        "schema": SCHEMA,
        "lens_fingerprint": lens["fingerprint"],
        "source_custody": custody,
        "source_custodian_key_id": signed_custody["key_id"],
        "signed_lineage_receipt_sha256": prior["fingerprint"],
        "signed_lineage": prior,
        "verdict": prior["verdict"],
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
        "blockers": sorted(set(prior["blockers"] + [
            "SOURCE_AUTHORITY_NOT_INDEPENDENTLY_VERIFIED",
            "CUSTODY_SIGNATURE_NOT_SEMANTIC_TRUTH",
            "DIFFERENT_CONTENT_HASHES_NOT_INDEPENDENT_ORIGINS",
        ] + (["IDENTICAL_CONTENT_ROOTS"] if custody["identical_content_root_groups"] else []))),
    }
    result["fingerprint"] = digest(result)
    return result
