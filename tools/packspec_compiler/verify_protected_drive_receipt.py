"""Independently replay a portable *human-signed* protected Drive decision.

Requires the exact original files, a trusted key list and separately supplied
owner subject/folder. This verifies approved claims and byte hashes, *not*
historic Google permissions, publisher truth or external audit anchoring.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives import serialization
from signed_bundles import verify, canonical, ATTEST_SCHEMA, SignatureError

SDK = Path(__file__).resolve().parents[2] / "sdk" / "python"
if str(SDK) not in sys.path:
    sys.path.insert(0, str(SDK))
from qualityrag import evaluate

SCHEMA = "qualityrag.protected-drive-decision-replay/v1"
KIND = "qualityrag.protected-drive-human-review/v1"
SHA = re.compile(r"^[a-f0-9]{64}$")
SOURCE = re.compile(r"^google_drive/[a-f0-9]{32}$")
MAX_RAW = 524_288


class ProtectedVerificationError(ValueError):
    pass


def need(ok, why):
    if not ok:
        raise ProtectedVerificationError(why)


def strict_read(file):
    raw = Path(file).read_bytes()
    need(0 < len(raw) <= MAX_RAW, "INVALID_RECEIPT_SIZE")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8", "strict"),
                          object_pairs_hook=pairs,
                          parse_float=lambda _: (_ for _ in ()).throw(ProtectedVerificationError("INVALID_FLOAT")),
                          parse_constant=lambda _: (_ for _ in ()).throw(ProtectedVerificationError("INVALID_CONSTANT")))
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, ProtectedVerificationError):
            raise
        raise ProtectedVerificationError("INVALID_JSON") from exc


def checksum(payload):
    return sha256(payload).hexdigest()


def load_trust(file):
    obj = strict_read(file)
    need(isinstance(obj, dict) and set(obj) == {"custodian", "meaningReviewer"},
         "INVALID_TRUST_ROLES")
    keys = {}
    for role in ("custodian", "meaningReviewer"):
        value = obj[role]
        need(isinstance(value, dict) and set(value) == {"keyId", "publicKeyPem"},
             "INVALID_TRUST_KEY")
        key = serialization.load_pem_public_key(value["publicKeyPem"].encode("ascii"))
        need(key.__class__.__name__ == "Ed25519PublicKey", "TRUST_KEY_NOT_ED25519")
        keys[role] = (value["keyId"], key)
    need(keys["custodian"][0] != keys["meaningReviewer"][0] and
         keys["custodian"][1].public_bytes(
             serialization.Encoding.Raw, serialization.PublicFormat.Raw) !=
         keys["meaningReviewer"][1].public_bytes(
             serialization.Encoding.Raw, serialization.PublicFormat.Raw),
         "REVIEW_SIGNERS_NOT_INDEPENDENT_KEYS")
    return keys


def verify_receipt(receipt, trusted, sources, owner_subject, folder_id):
    need(isinstance(receipt, dict) and set(receipt) == {
        "schema", "id", "serviceId", "environment", "at", "asOf",
        "policy", "policySha256", "evidence", "result",
        "signedCustody", "signedMeaning", "claim",
        "sourceTruthProven", "independentOriginsProven",
        "externallyAnchored", "chainHash"
    }, "INVALID_PROTECTED_RECEIPT")
    need(receipt["schema"] == SCHEMA, "INVALID_RECEIPT_SCHEMA")
    need(receipt["sourceTruthProven"] is False and
         receipt["independentOriginsProven"] is False and
         receipt["externallyAnchored"] is False,
         "UNSUPPORTED_AUTHENTICITY_CLAIM")
    pack = receipt["policy"]
    need(isinstance(pack, dict) and set(pack) == {"id", "version", "requirements"},
         "INVALID_PACKSPEC")
    # JS RegistryStore hashes the serialized, unsorted, already normalized
    # PackSpec in the exact field order shown in its validator.
    reconstructed = {
        "id": pack["id"], "version": pack["version"], "requirements": pack["requirements"]
    }
    need(all(isinstance(req, dict) and
        set(req).issubset({"id", "min_independent_sources", "max_age_seconds"}) and
        (req.get("min_independent_sources", 1) == 1) and
        "max_age_seconds" not in req for req in pack["requirements"]),
         "UNSUPPORTED_PACKSPEC_REQUIREMENT")
    need(isinstance(receipt["policySha256"], str) and
         SHA.fullmatch(receipt["policySha256"]) and
         checksum(json.dumps(reconstructed, ensure_ascii=False,
                 separators=(",", ":")).encode("utf8")) == receipt["policySha256"],
         "POLICY_DIGEST_MISMATCH")
    signed = []
    for role, envelope_key in [
        ("custodian", "signedCustody"), ("meaningReviewer", "signedMeaning")
    ]:
        envelope = receipt[envelope_key]
        key_id, public_key = trusted[role]
        need(isinstance(envelope, dict) and envelope.get("key_id") == key_id,
             "UNTRUSTED_REVIEW_SIGNER")
        signed.append(verify(envelope, {key_id: public_key}, schema=ATTEST_SCHEMA))
    need(canonical(signed[0]) == canonical(signed[1]), "SIGNERS_DISAGREE")
    payload = signed[0]
    need(payload.get("service") == receipt["serviceId"] and
         payload.get("environment") == receipt["environment"] and
         payload.get("policy_signature") ==
         "UNSIGNED-V0.1-PACK-SHA256:" + receipt["policySha256"],
         "REVIEW_SCOPE_OR_POLICY_MISMATCH")
    observations = payload.get("observations")
    need(isinstance(observations, dict) and
         observations.get("kind") == KIND and
         observations.get("folder_id") == folder_id and
         observations.get("owner_binding") ==
         checksum(("qualityrag.review-owner/v1:" + owner_subject).encode("utf-8")) and
         observations.get("review_basis") == "HUMAN_SEMANTIC_APPROVAL" and
         observations.get("origin_basis") == "CUSTODIAN_ATTESTED",
         "REVIEW_OWNER_SCOPE_MISMATCH")
    witnesses = payload.get("witnesses")
    need(isinstance(witnesses, list) and 1 <= len(witnesses) <= 8,
         "INVALID_WITNESSES")
    need(set(sources) == {w.get("sourceId") for w in witnesses},
         "SOURCE_BYTES_NOT_SUPPLIED")
    as_of = receipt["asOf"]
    evidence = []
    for i, w in enumerate(witnesses):
        need(isinstance(w, dict) and set(w) == {
            "sourceId", "revision", "requirementId", "lineNumber",
            "lineSha256", "origin", "status"
        }, "INVALID_WITNESS")
        source_id = w["sourceId"]
        need(isinstance(source_id, str) and SOURCE.fullmatch(source_id) and
             type(w["lineNumber"]) is int and w["lineNumber"] > 0,
             "INVALID_WITNESS")
        data = Path(sources[source_id]).read_bytes()
        need(0 < len(data) <= 96_000 and checksum(data) == w["revision"],
             "SOURCE_BYTES_REVISION_MISMATCH")
        lines = data.decode("utf8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        need(w["lineNumber"] <= len(lines) and
             checksum(lines[w["lineNumber"] - 1].encode("utf8")) == w["lineSha256"],
             "SOURCE_ANCHOR_MISMATCH")
        evidence.append({
            "id": "ev_" + checksum(
                f"human-attested:{i}:{source_id}:{w['lineNumber']}".encode("utf8"))[:32],
            "requirement_id": w["requirementId"],
            "origin": w["origin"],
            "source_ref": "src_" + checksum(source_id.encode("utf8"))[:32],
            "status": w["status"],
            "observed_at": as_of
        })
    need(receipt["evidence"] == evidence, "DERIVED_EVIDENCE_MISMATCH")
    replay = evaluate(pack, evidence, as_of=as_of)
    need(replay == receipt["result"], "INDEPENDENT_REPLAY_MISMATCH")
    return {
        "verified": True, "signatureCount": 2,
        "originalBytesMatched": True, "independentReplayMatched": True,
        "reportedVerdict": replay["verdict"], "sourceCount": len(sources),
        "meaningProvenAutomatically": False, "publisherAuthenticated": False,
        "historicalGoogleAccessVerified": False, "externallyAnchored": False
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Independently verify signed QualityRAG protected decision")
    p.add_argument("--receipt", required=True)
    p.add_argument("--trust", required=True)
    p.add_argument("--owner-subject", required=True)
    p.add_argument("--folder-id", required=True)
    p.add_argument("--source", action="append", required=True,
                   help="google_drive/opaque-source-id=/absolute/local/byte-exact/file")
    args = p.parse_args(argv)
    try:
        files = {}
        for pair in args.source:
            need("=" in pair, "INVALID_SOURCE_MAPPING")
            ref, pathname = pair.split("=", 1)
            need(ref not in files and SOURCE.fullmatch(ref) and pathname,
                 "INVALID_SOURCE_MAPPING")
            files[ref] = pathname
        result = verify_receipt(
            strict_read(args.receipt), load_trust(args.trust), files,
            args.owner_subject, args.folder_id
        )
        print(json.dumps(result, indent=2))
        return 0
    except (ProtectedVerificationError, SignatureError, KeyError,
            TypeError, ValueError, OSError) as exc:
        print(json.dumps({"verified": False, "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
