"""Independent, offline replay of a QualityRAG registry evidence export.

Verifies a *declared metadata* gate result using the independent Python SDK.
This does not authenticate original source documents, identities, or ledger custody.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from qualityrag import evaluate


class ReceiptVerificationError(ValueError):
    """Receipt cannot be independently replayed as claimed."""


_HEX = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^(ev|org|src)_[0-9a-f]{24,64}$")
_VERDICT = {"ADMIT", "REFUSE", "INCONCLUSIVE"}


def _hash(value: Any) -> str:
    # Matches JSON.stringify for the restricted v0.1 contract:
    # insertion-ordered objects, finite integers, strings and arrays.
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def _object_keys(value: Any, exact: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != exact:
        raise ReceiptVerificationError("INVALID_" + label)


def verify_package(
    document: dict[str, Any],
    *,
    trusted_sha256: str | None = None,
    trusted_policy_sha256: str | None = None,
) -> dict[str, Any]:
    """Replay a registry export without network access or Studio authority.

    To check authenticity of the export *bytes*, obtain a SHA-256 commitment
    through an independently trusted channel and provide trusted_sha256.
    Otherwise the embedded hash merely catches accidental/incomplete changes.
    Source authenticity remains unverified regardless of digest matching.
    """
    _object_keys(document, {"payload", "integrity"}, "EXPORT_WRAPPER")
    payload = document["payload"]
    integrity = document["integrity"]
    _object_keys(
        integrity,
        {"sha256", "externallyAnchored", "digitallySigned", "authenticityVerified"},
        "INTEGRITY_RECORD",
    )
    if any(integrity[k] is not False for k in
           ("externallyAnchored", "digitallySigned", "authenticityVerified")):
        raise ReceiptVerificationError("UNSUPPORTED_AUTHENTICITY_CLAIM")
    if not isinstance(integrity["sha256"], str) or not _HEX.fullmatch(integrity["sha256"]):
        raise ReceiptVerificationError("INVALID_EXPORT_HASH")
    _object_keys(payload, {
        "schema", "evaluationId", "serviceId", "environment", "requestId",
        "traceId", "asOf", "evaluator", "policy", "policySha256", "evidence",
        "expectedResult", "sourceOriginStatus", "ledgerRecordHash",
    }, "EXPORT_PAYLOAD")
    if payload["schema"] != "qualityrag.evidence-replay/v1" or (
        payload["evaluator"] != "qualityrag.registry-metadata-gate/v1"
    ) or payload["sourceOriginStatus"] != "CALLER_DECLARED_NOT_AUTHENTICATED":
        raise ReceiptVerificationError("UNSUPPORTED_EXPORT_CONTRACT")
    for key in ("evaluationId", "serviceId", "environment", "requestId", "traceId"):
        if not isinstance(payload[key], str) or not 1 <= len(payload[key]) <= 128:
            raise ReceiptVerificationError("INVALID_EVENT_IDENTITY")
    if not isinstance(payload["ledgerRecordHash"], str) or not _HEX.fullmatch(
        payload["ledgerRecordHash"]
    ):
        raise ReceiptVerificationError("INVALID_LEDGER_HASH")
    if not isinstance(payload["policySha256"], str) or not _HEX.fullmatch(
        payload["policySha256"]
    ):
        raise ReceiptVerificationError("INVALID_POLICY_HASH")
    if _hash(payload) != integrity["sha256"]:
        raise ReceiptVerificationError("EXPORT_DIGEST_MISMATCH")
    if trusted_sha256 is not None and (
        not _HEX.fullmatch(trusted_sha256) or trusted_sha256 != integrity["sha256"]
    ):
        raise ReceiptVerificationError("TRUSTED_EXPORT_DIGEST_MISMATCH")

    pack = payload["policy"]
    _object_keys(pack, {"id", "version", "requirements"}, "PACKSPEC")
    if not isinstance(pack["id"], str) or not pack["id"] or (
        not isinstance(pack["version"], str) or not pack["version"]
    ):
        raise ReceiptVerificationError("INVALID_PACKSPEC_ID")
    if not isinstance(pack["requirements"], list) or (
        not 1 <= len(pack["requirements"]) <= 100
    ):
        raise ReceiptVerificationError("INVALID_REQUIREMENTS")
    seen = set()
    for requirement in pack["requirements"]:
        if not isinstance(requirement, dict) or not set(requirement).issubset({
            "id", "min_independent_sources", "max_age_seconds"
        }) or "id" not in requirement:
            raise ReceiptVerificationError("UNSUPPORTED_REQUIREMENT")
        rid = requirement["id"]
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ReceiptVerificationError("INVALID_REQUIREMENTS")
        seen.add(rid)
        for key in ("min_independent_sources", "max_age_seconds"):
            if key in requirement and (
                type(requirement[key]) is not int or
                requirement[key] < (1 if key == "min_independent_sources" else 0)
            ):
                raise ReceiptVerificationError("INVALID_REQUIREMENT_THRESHOLD")
    if _hash(pack) != payload["policySha256"]:
        raise ReceiptVerificationError("POLICY_DIGEST_MISMATCH")
    if trusted_policy_sha256 is not None and (
        not _HEX.fullmatch(trusted_policy_sha256) or
        payload["policySha256"] != trusted_policy_sha256
    ):
        raise ReceiptVerificationError("TRUSTED_POLICY_DIGEST_MISMATCH")

    evidence = payload["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 100:
        raise ReceiptVerificationError("INVALID_EVIDENCE_SET")
    ids = set()
    for record in evidence:
        _object_keys(record, {
            "id", "requirement_id", "origin", "source_ref", "status", "observed_at",
        }, "EVIDENCE_RECORD")
        if any(not isinstance(record[key], str) for key in record):
            raise ReceiptVerificationError("INVALID_EVIDENCE_TYPE")
        if any(not _TOKEN.fullmatch(record[key]) for key in
               ("id", "origin", "source_ref")) or record["id"] in ids or (
            record["requirement_id"] not in seen
        ) or record["status"] not in {"SUPPORTS", "CONTRADICTS", "UNKNOWN"}:
            raise ReceiptVerificationError("INVALID_EVIDENCE_RECORD")
        ids.add(record["id"])
    if not isinstance(payload["asOf"], str) or not payload["asOf"].endswith("Z"):
        raise ReceiptVerificationError("INVALID_REPLAY_TIME")
    try:
        replay = evaluate(pack, evidence, as_of=payload["asOf"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReceiptVerificationError("REPLAY_INPUT_INVALID") from exc
    recorded = payload["expectedResult"]
    if not isinstance(recorded, dict) or recorded.get("verdict") not in _VERDICT:
        raise ReceiptVerificationError("INVALID_RECORDED_RESULT")
    if replay != recorded:
        raise ReceiptVerificationError("INDEPENDENT_REPLAY_MISMATCH")
    return {
        "verified": True,
        "scope": "independent_python_metadata_replay_only",
        "evaluationId": payload["evaluationId"],
        "verdict": replay["verdict"],
        "requirementsChecked": len(replay["findings"]),
        "exportDigestMatched": True,
        "policyDigestMatched": True,
        "trustedExportDigestMatched": trusted_sha256 is not None,
        "trustedPolicyDigestMatched": trusted_policy_sha256 is not None,
        "sourceAuthenticityVerified": False,
        "customerIdentityVerified": False,
        "ledgerChainIndependentlyVerified": False,
        "complianceCertified": False,
    }


def _no_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in items:
        if key in result:
            raise ReceiptVerificationError("DUPLICATE_JSON_KEY")
        result[key] = val
    return result


def _invalid_constant(value: str) -> None:
    raise ReceiptVerificationError("INVALID_JSON_NUMBER")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently replay a metadata-only QualityRAG evidence export."
    )
    parser.add_argument("file", type=Path, help="JSON export from the registry")
    parser.add_argument("--trusted-sha256", help="SHA-256 from a separate trusted channel")
    parser.add_argument("--trusted-policy-sha256", help="Approved policy digest from a trusted channel")
    args = parser.parse_args(argv)
    try:
        raw = args.file.read_bytes()
        if len(raw) > 1_000_000:
            raise ReceiptVerificationError("RECEIPT_TOO_LARGE")
        document = json.loads(
            raw, object_pairs_hook=_no_duplicates, parse_constant=_invalid_constant
        )
        verdict = verify_package(
            document,
            trusted_sha256=args.trusted_sha256,
            trusted_policy_sha256=args.trusted_policy_sha256,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"verified": False, "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
