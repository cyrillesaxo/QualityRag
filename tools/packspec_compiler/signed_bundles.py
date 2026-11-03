"""Versioned, Ed25519-signed QualityRag policy and evidence bundles.

Canonical format QR-CJSON-1: UTF-8 JSON; sorted keys; no floats; no duplicate
keys in parsed documents; bounded inputs; domain-separated signatures.
This is NOT RFC 8785 / JCS and cross-language interoperability is not claimed.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

POLICY_SCHEMA = "qualityrag.signed-policy/v1"
ATTEST_SCHEMA = "qualityrag.signed-observations/v1"
CANONICAL = "QR-CJSON-1"
MAX_DOCUMENT_BYTES = 524_288
MAX_VALIDITY_SECONDS = 86_400 * 30
ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

class SignatureError(ValueError):
    pass


def _fail(condition: bool, message: str) -> None:
    if not condition:
        raise SignatureError(message)


def _primitive(value: Any, depth: int = 0) -> None:
    _fail(depth < 40, "JSON nesting too deep")
    if isinstance(value, dict):
        for key, item in value.items():
            _fail(isinstance(key, str) and len(key) <= 160, "Invalid JSON key")
            _primitive(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _primitive(item, depth + 1)
    elif type(value) in (str, int, bool) or value is None:
        if type(value) is str:
            _fail(len(value) <= 50_000, "JSON string too long")
    else:
        raise SignatureError("Only integer, string, boolean, null and JSON collections supported; floats prohibited")


def canonical(value: Any) -> bytes:
    """Small, deterministic restricted JSON format, not an IETF JCS implementation."""
    _primitive(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    _fail(len(raw) <= MAX_DOCUMENT_BYTES, "Canonical JSON exceeds size bound")
    return raw


def load_canonical_json(raw: bytes) -> Any:
    """Reject duplicates, invalid UTF-8 and alternate encodings on transport."""
    _fail(isinstance(raw, bytes) and 0 < len(raw) <= MAX_DOCUMENT_BYTES, "Invalid JSON input size")
    def pairs(entries):
        result = {}
        for key, value in entries:
            _fail(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                           parse_float=lambda _: (_ for _ in ()).throw(SignatureError("Floats prohibited")),
                           parse_constant=lambda _: (_ for _ in ()).throw(SignatureError("Nonfinite values prohibited")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SignatureError("Malformed JSON") from exc
    _fail(canonical(value) == raw, "Noncanonical JSON encoding")
    return value


def _instant(raw: str) -> datetime:
    _fail(isinstance(raw, str), "Timestamp must be a string")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Naive timestamp")
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SignatureError("Invalid timestamp") from exc


def _validate_period(issued: str, expires: str, as_of: str) -> None:
    start, end, now = _instant(issued), _instant(expires), _instant(as_of)
    _fail(start < end and (end - start).total_seconds() <= MAX_VALIDITY_SECONDS, "Invalid validity interval")
    _fail(start <= now < end, "Signature expired or not yet valid")


def _label(raw: Any, name: str) -> str:
    _fail(isinstance(raw, str) and ID.fullmatch(raw) is not None, "Invalid " + name)
    return raw


def _domain(schema: str) -> bytes:
    return ("QUALITYRAG/" + schema + "\x00").encode("ascii")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    _fail(isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_-]{86}", s) is not None,
          "Invalid signature encoding")
    try:
        raw = base64.urlsafe_b64decode(s + "==")
    except (ValueError, base64.binascii.Error) as exc:
        raise SignatureError("Malformed signature") from exc
    _fail(len(raw) == 64 and _b64(raw) == s, "Noncanonical signature")
    return raw


def sign(payload: dict, key: Ed25519PrivateKey, *, key_id: str, schema: str) -> dict:
    _fail(schema in (POLICY_SCHEMA, ATTEST_SCHEMA), "Unknown signature domain")
    _fail(isinstance(key, Ed25519PrivateKey), "Invalid signing key")
    _label(key_id, "key ID")
    _fail(isinstance(payload, dict), "Signed payload must be object")
    body = canonical(payload)
    sig = key.sign(_domain(schema) + body)
    return {"schema": schema, "canonical": CANONICAL, "key_id": key_id,
            "payload": payload, "signature": _b64(sig)}


def verify(envelope: dict, trusted_keys: dict[str, Ed25519PublicKey], *,
           schema: str) -> dict:
    _fail(isinstance(envelope, dict) and set(envelope) ==
          {"schema", "canonical", "key_id", "payload", "signature"}, "Invalid signed envelope")
    _fail(envelope["schema"] == schema and envelope["canonical"] == CANONICAL,
          "Unsupported signature format")
    kid = _label(envelope["key_id"], "key ID")
    _fail(isinstance(trusted_keys, dict) and kid in trusted_keys, "Unknown or revoked key")
    key = trusted_keys[kid]
    _fail(isinstance(key, Ed25519PublicKey), "Invalid public key")
    _fail(isinstance(envelope["payload"], dict), "Invalid payload")
    try:
        key.verify(_unb64(envelope["signature"]), _domain(schema) + canonical(envelope["payload"]))
    except InvalidSignature as exc:
        raise SignatureError("Signature verification failed") from exc
    return envelope["payload"]


def sign_policy(ir: dict, key: Ed25519PrivateKey, *, key_id: str,
                service: str, environment: str, sequence: int,
                issued_at: str, expires_at: str) -> dict:
    from typed_ir import IR_SCHEMA, _fingerprint
    _fail(isinstance(ir, dict) and ir.get("schema") == IR_SCHEMA, "Invalid IR schema")
    source = ir.get("source", {})
    _fail(isinstance(source, dict) and isinstance(source.get("sha256"), str) and
          re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None, "Invalid source digest")
    _fail(_fingerprint({"source_sha256": source["sha256"], "nodes": ir.get("nodes")}) ==
          ir.get("ir_sha256"), "IR digest mismatch")
    _fail(type(sequence) is int and sequence > 0, "Invalid sequence")
    _validate_period(issued_at, expires_at, issued_at)
    payload = {"ir": ir, "service": _label(service, "service"), "environment": _label(environment, "environment"),
               "sequence": sequence, "issued_at": issued_at, "expires_at": expires_at}
    return sign(payload, key, key_id=key_id, schema=POLICY_SCHEMA)


def verify_policy(bundle: dict, trusted_keys: dict[str, Ed25519PublicKey], *,
                  service: str, environment: str, as_of: str,
                  minimum_sequence: int) -> dict:
    from typed_ir import IR_SCHEMA, _fingerprint
    p = verify(bundle, trusted_keys, schema=POLICY_SCHEMA)
    _fail(p.get("service") == service and p.get("environment") == environment,
          "Policy service/environment mismatch")
    _fail(type(minimum_sequence) is int and minimum_sequence > 0 and
          type(p.get("sequence")) is int and p["sequence"] >= minimum_sequence,
          "Policy sequence rollback")
    _validate_period(p.get("issued_at"), p.get("expires_at"), as_of)
    ir = p.get("ir")
    _fail(isinstance(ir, dict) and ir.get("schema") == IR_SCHEMA, "Invalid IR")
    source = ir.get("source")
    _fail(isinstance(source, dict) and isinstance(source.get("sha256"), str), "Invalid source")
    _fail(_fingerprint({"source_sha256": source["sha256"], "nodes": ir.get("nodes")}) ==
          ir.get("ir_sha256"), "IR digest mismatch")
    return p


def sign_attestation(witnesses: list[dict], observations: dict, key: Ed25519PrivateKey,
                     *, key_id: str, policy_signature: str,
                     service: str, environment: str, nonce: str,
                     issued_at: str, expires_at: str) -> dict:
    _fail(isinstance(witnesses, list) and isinstance(observations, dict), "Invalid inputs")
    _fail(isinstance(policy_signature, str) and bool(policy_signature), "Missing policy binding")
    _validate_period(issued_at, expires_at, issued_at)
    payload = {"service": _label(service, "service"), "environment": _label(environment, "environment"),
               "policy_signature": policy_signature, "nonce": _label(nonce, "nonce"),
               "issued_at": issued_at, "expires_at": expires_at,
               "witnesses": witnesses, "observations": observations}
    return sign(payload, key, key_id=key_id, schema=ATTEST_SCHEMA)


def verify_attestation(attestation: dict, trusted_keys: dict[str, Ed25519PublicKey],
                       *, policy_signature: str, service: str, environment: str,
                       as_of: str, witnesses: list[dict], observations: dict,
                       nonce_accepted: Callable[[str, str, str], bool]) -> bool:
    """Caller must atomically reject previously used nonces in durable state.

    Acceptance proves a trusted signing key signed the exact supplied records;
    it does not prove physical truth or independence of the signer.
    """
    p = verify(attestation, trusted_keys, schema=ATTEST_SCHEMA)
    _fail(p.get("service") == service and p.get("environment") == environment and
          p.get("policy_signature") == policy_signature, "Attestation binding mismatch")
    _validate_period(p.get("issued_at"), p.get("expires_at"), as_of)
    _fail(canonical(p.get("witnesses")) == canonical(witnesses) and
          canonical(p.get("observations")) == canonical(observations),
          "Attestation does not match evaluated inputs")
    nonce = _label(p.get("nonce"), "nonce")
    _fail(callable(nonce_accepted), "Durable replay guard is required")
    _fail(nonce_accepted(service, environment, nonce) is True, "Attestation replay or nonce rejected")
    return True
