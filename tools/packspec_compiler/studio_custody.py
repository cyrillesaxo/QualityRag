"""Customer-controlled source custody for portable Studio Evidence Assurance receipts.

Reuses QualityRAG's existing QR-CJSON-1 / Ed25519 signed-observations
envelope (signed_bundles.py), not a new cryptographic signature format.

A signature proves a configured custodian signed a claimed mapping of opaque
source IDs, declared origins and exact local bytes. This does not authenticate
real-world publishers, semantic correctness, independence, or completeness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_SDK = Path(__file__).resolve().parents[2] / "sdk" / "python"
if str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))
from qualityrag.verify_receipt import verify_package
from signed_bundles import ATTEST_SCHEMA, sign_attestation, verify, SignatureError

SCHEMA = "qualityrag.studio-source-custody/v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
SRC = re.compile(r"^src_[0-9a-f]{24,64}$")
ORIGIN = re.compile(r"^org_[0-9a-f]{24,64}$")
MAX_SOURCE_BYTES = 2_000_000
MAX_PACKAGE_BYTES = 524_288
MAX_SOURCES = 100


class CustodyError(ValueError):
    """Source inventory, payload or custody signature is not acceptable."""


def _require(condition, message):
    if not condition:
        raise CustodyError(message)


def _strict_json(path):
    raw = Path(path).read_bytes()
    _require(0 < len(raw) <= MAX_PACKAGE_BYTES, "INVALID_JSON_SIZE")
    def pairs(items):
        value = {}
        for k, v in items:
            _require(k not in value, "DUPLICATE_JSON_KEY")
            value[k] = v
        return value
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(CustodyError("INVALID_JSON_NUMBER")),
            parse_float=lambda x: (_ for _ in ()).throw(CustodyError("FLOATS_NOT_SUPPORTED")))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, CustodyError):
            raise
        raise CustodyError("MALFORMED_JSON") from exc


def _sha(value):
    return sha256(value).hexdigest()


def _time(value):
    _require(isinstance(value, str) and value.endswith("Z"), "INVALID_CUSTODY_TIME")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise CustodyError("INVALID_CUSTODY_TIME") from exc
    _require(at.tzinfo is not None, "INVALID_CUSTODY_TIME")
    return at.astimezone(timezone.utc)


def _source_bytes(source_files):
    _require(isinstance(source_files, dict) and
             0 < len(source_files) <= MAX_SOURCES, "INVALID_SOURCE_FILE_MAP")
    data = {}
    for ref, filename in source_files.items():
        _require(isinstance(ref, str) and SRC.fullmatch(ref) is not None,
                 "INVALID_SOURCE_REFERENCE")
        item = Path(filename)
        _require(not item.is_symlink() and item.is_file(), "INVALID_SOURCE_FILE")
        length = item.stat().st_size
        _require(0 < length <= MAX_SOURCE_BYTES, "SOURCE_SIZE_OUT_OF_BOUNDS")
        content = item.read_bytes()
        _require(len(content) == length, "SOURCE_CHANGED_WHILE_READING")
        data[ref] = (_sha(content), len(content))
    return data


def _validate_manifest(receipt, manifest, source_files):
    verified = verify_package(receipt)  # independent v0.1 metadata evaluator
    payload = receipt["payload"]
    _require(isinstance(manifest, dict) and set(manifest) ==
             {"schema", "evaluationId", "serviceId", "environment", "policySha256", "sources"},
             "INVALID_CUSTODY_MANIFEST")
    _require(manifest["schema"] == SCHEMA, "UNSUPPORTED_CUSTODY_MANIFEST")
    for key in ("evaluationId", "serviceId", "environment", "policySha256"):
        _require(manifest[key] == payload[key], "CUSTODY_RECEIPT_BINDING_MISMATCH")
    sources = manifest["sources"]
    _require(isinstance(sources, list) and 0 < len(sources) <= MAX_SOURCES,
             "INVALID_CUSTODY_SOURCES")
    by_ref = {}
    for row in sources:
        _require(isinstance(row, dict) and set(row) ==
                 {"source_ref", "declared_origin", "content_sha256", "content_length"},
                 "INVALID_CUSTODY_ROW")
        ref, org = row["source_ref"], row["declared_origin"]
        _require(isinstance(ref, str) and SRC.fullmatch(ref) is not None and ref not in by_ref
                 and isinstance(org, str) and ORIGIN.fullmatch(org) is not None
                 and isinstance(row["content_sha256"], str)
                 and HEX.fullmatch(row["content_sha256"]) is not None
                 and type(row["content_length"]) is int
                 and 0 < row["content_length"] <= MAX_SOURCE_BYTES,
                 "INVALID_CUSTODY_ROW")
        by_ref[ref] = row
    expected = {}
    for item in payload["evidence"]:
        ref, org = item["source_ref"], item["origin"]
        if ref in expected and expected[ref] != org:
            raise CustodyError("CONFLICTING_SOURCE_ORIGINS_IN_RECEIPT")
        expected[ref] = org
    _require(set(expected) == set(by_ref), "MISSING_OR_UNRELATED_CUSTODY_SOURCE")
    for ref, org in expected.items():
        _require(by_ref[ref]["declared_origin"] == org, "DECLARED_ORIGIN_MISMATCH")
    actual = _source_bytes(source_files)
    _require(set(actual) == set(by_ref), "MISSING_EXACT_SOURCE_BYTES")
    digest_to_origins = {}
    for ref, row in by_ref.items():
        got_hash, got_size = actual[ref]
        _require(row["content_sha256"] == got_hash and row["content_length"] == got_size,
                 "SOURCE_CONTENT_DIGEST_MISMATCH")
        digest_to_origins.setdefault(got_hash, set()).add(row["declared_origin"])
    _require(not any(len(origins) > 1 for origins in digest_to_origins.values()),
             "IDENTICAL_BYTES_CLAIM_DIFFERENT_ORIGINS")
    return verified


def _policy_binding(sha_value):
    _require(isinstance(sha_value, str) and HEX.fullmatch(sha_value) is not None,
             "INVALID_POLICY_SHA")
    # Existing signature field names this 'policy_signature'; we expressly bind
    # a *digest of the unsigned v0.1 PackSpec*, NOT a signed policy.
    return "UNSIGNED-V0.1-PACK-SHA256:" + sha_value


def _observation(manifest):
    return {"studio_custody": manifest}


def _validate_binding(signed, manifest, public_key, *, as_of=None):
    _require(isinstance(signed, dict), "INVALID_SIGNED_CUSTODY")
    kid = signed.get("key_id")
    _require(isinstance(kid, str) and kid, "INVALID_CUSTODY_KEY_ID")
    payload = verify(signed, {kid: public_key}, schema=ATTEST_SCHEMA)
    _require(isinstance(payload, dict) and set(payload) == {
        "service", "environment", "policy_signature", "nonce", "issued_at",
        "expires_at", "witnesses", "observations"}, "INVALID_SIGNED_CUSTODY_PAYLOAD")
    _require(payload["service"] == manifest["serviceId"] and
             payload["environment"] == manifest["environment"] and
             payload["policy_signature"] == _policy_binding(manifest["policySha256"]) and
             payload["witnesses"] == [] and payload["observations"] == _observation(manifest),
             "CUSTODY_SIGNATURE_NOT_BOUND_TO_RECEIPT")
    _require(isinstance(payload["nonce"], str) and
             re.fullmatch(r"[A-Za-z0-9._-]{1,128}", payload["nonce"]) is not None,
             "INVALID_CUSTODY_NONCE")
    issued, expires = _time(payload["issued_at"]), _time(payload["expires_at"])
    now = as_of if as_of is not None else datetime.now(timezone.utc)
    _require(issued < expires and expires - issued <= timedelta(days=30)
             and issued <= now < expires, "CUSTODY_SIGNATURE_EXPIRED_OR_NOT_YET_VALID")
    return kid


def sign_customer_manifest(*, receipt, manifest, source_files,
                           private_key, key_id, nonce, expires_seconds=86400):
    """Require customer-curated approved origins, actual source bytes and a key.

    Do not derive the manifest from the potentially attacker-controlled receipt.
    The caller must review the source-to-origin mapping separately.
    """
    _validate_manifest(receipt, manifest, source_files)
    _require(isinstance(private_key, Ed25519PrivateKey), "INVALID_CUSTODIAN_KEY")
    _require(type(expires_seconds) is int and 1 <= expires_seconds <= 86400*30,
             "INVALID_CUSTODY_VALIDITY")
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(seconds=expires_seconds)
    return sign_attestation([], _observation(manifest), private_key,
        key_id=key_id, policy_signature=_policy_binding(manifest["policySha256"]),
        service=manifest["serviceId"], environment=manifest["environment"],
        nonce=nonce, issued_at=issued.isoformat().replace("+00:00", "Z"),
        expires_at=expires.isoformat().replace("+00:00", "Z"))


def verify_customer_manifest(*, receipt, signed_custody, public_key, source_files,
                             as_of=None):
    """Verify a separately trusted custodian's signature and exact local bytes.

    Evidence status and source-origin independence are NOT authenticated by this.
    """
    _require(isinstance(public_key, Ed25519PublicKey), "INVALID_CUSTODIAN_PUBLIC_KEY")
    _require(isinstance(signed_custody, dict), "INVALID_CUSTODY_ATTESTATION")
    signed_payload = signed_custody.get("payload")
    _require(isinstance(signed_payload, dict), "INVALID_SIGNED_CUSTODY_PAYLOAD")
    observations = signed_payload.get("observations")
    _require(isinstance(observations, dict) and set(observations) == {"studio_custody"},
             "INVALID_CUSTODY_OBSERVATIONS")
    manifest = observations["studio_custody"]
    verified = _validate_manifest(receipt, manifest, source_files)
    kid = _validate_binding(signed_custody, manifest, public_key, as_of=as_of)
    return {
        "metadataReplayVerified": verified["verified"],
        "sourceCustodyVerified": True,
        "custodyLevel": "SIGNED_CLAIM_AND_EXACT_SUPPLIED_BYTES",
        "custodianKeyId": kid,
        "custodySourceCount": len(manifest["sources"]),
        "evaluationId": manifest["evaluationId"],
        "policySha256": manifest["policySha256"],
        "sourcePublisherAuthenticated": False,
        "sourceIndependenceProven": False,
        "evidenceSemanticsVerified": False,
        "policyCompletenessProven": False,
        "complianceCertified": False,
        "signatureReplayProtection": False,
    }


def _parse_sources(items):
    mapping = {}
    for item in items:
        _require("=" in item, "INVALID_SOURCE_MAPPING")
        ref, filename = item.split("=", 1)
        _require(ref not in mapping and ref and filename, "INVALID_SOURCE_MAPPING")
        mapping[ref] = filename
    return mapping


def _write_new(file, value):
    dest = Path(file)
    _require(not dest.exists() and not dest.is_symlink(), "CUSTODY_OUTPUT_EXISTS")
    handle = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(value, out, indent=2, ensure_ascii=False)
            out.write("\n")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def _load_key(path, *, private):
    file = Path(path)
    _require(not file.is_symlink() and file.is_file(), "INVALID_KEY_PATH")
    if private and os.name == "posix":
        _require(stat.S_IMODE(file.stat().st_mode) & 0o077 == 0,
                 "PRIVATE_KEY_PERMISSIONS_TOO_BROAD")
    data = file.read_bytes()
    result = (serialization.load_pem_private_key(data, password=None) if private
              else serialization.load_pem_public_key(data))
    expected = Ed25519PrivateKey if private else Ed25519PublicKey
    _require(isinstance(result, expected), "ED25519_KEY_REQUIRED")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sign or verify customer source custody for a QualityRAG replay.")
    sub = parser.add_subparsers(dest="command", required=True)
    sign = sub.add_parser("sign", help="Custodian signs separately reviewed manifest and checked source bytes")
    sign.add_argument("--receipt", required=True)
    sign.add_argument("--manifest", required=True)
    sign.add_argument("--private-key", required=True)
    sign.add_argument("--key-id", required=True)
    sign.add_argument("--nonce", required=True)
    sign.add_argument("--out", required=True)
    sign.add_argument("--source", action="append", required=True, help="source_token=/local/exact/file")
    check = sub.add_parser("verify", help="Review signed custody using an out-of-band trusted public key")
    check.add_argument("--receipt", required=True)
    check.add_argument("--attestation", required=True)
    check.add_argument("--public-key", required=True)
    check.add_argument("--source", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = _strict_json(args.receipt)
        sources = _parse_sources(args.source)
        if args.command == "sign":
            manifest = _strict_json(args.manifest)
            key = _load_key(args.private_key, private=True)
            signed = sign_customer_manifest(
                receipt=receipt, manifest=manifest, source_files=sources,
                private_key=key, key_id=args.key_id, nonce=args.nonce)
            _write_new(args.out, signed)
            result = {"signed": True, "out": args.out, "sourceCount": len(sources),
                      "warning": "Signer attests bytes and *customer-reviewed declared origin mapping*, not source truth."}
        else:
            key = _load_key(args.public_key, private=False)
            attestation = _strict_json(args.attestation)
            result = verify_customer_manifest(
                receipt=receipt, signed_custody=attestation,
                public_key=key, source_files=sources)
    except (CustodyError, SignatureError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({"verified": False, "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
