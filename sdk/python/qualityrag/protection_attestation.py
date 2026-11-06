"""Reference attestation for purpose-bound views (stdlib only).

HMAC is a local demonstration of trusted registry attestations, NOT a production
key-management system. Keep signing keys and these functions inside a trusted
service; never expose them to the model or untrusted tenants.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any, Protocol

from .protection import Principal, ProtectionDenied, protect, authorize_release, SCHEMA
from .protection_lifecycle import InMemoryPolicyAuthority

class ReplayLedger(Protocol):
    def consume(self, nonce: str, expires_at: int, now: int) -> bool: ...


class PolicyRegistry(Protocol):
    def require_active(self, *, tenant: str, policy_id: str, version: int) -> None: ...


CONTRACT_VERSION = "qualityrag.contract-attestation/v0.1"
RECEIPT_VERSION = "qualityrag.release-receipt/v0.1"


def _canonical(data: dict[str, Any]) -> bytes:
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProtectionDenied("INVALID_ATTESTATION_DATA") from exc


def _key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ProtectionDenied("INVALID_KEY")
    return key


def _mac(data: dict[str, Any], key: bytes) -> str:
    return hmac.new(_key(key), _canonical(data), hashlib.sha256).hexdigest()


def attest_contract(contract: dict[str, Any], key: bytes) -> dict[str, Any]:
    """Trusted registry only: sign contract version, tenant and field grants."""
    if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
        raise ProtectionDenied("INVALID_CONTRACT")
    # The legacy boolean is deliberately excluded from the signed contract.
    payload = {k: v for k, v in contract.items() if k != "authenticated"}
    return {"version": CONTRACT_VERSION, "payload": payload,
            "signature": _mac({"version": CONTRACT_VERSION, "payload": payload}, key)}


def _verify_contract(attestation: dict[str, Any], key: bytes) -> dict[str, Any]:
    if not isinstance(attestation, dict) or set(attestation) != {"version", "payload", "signature"}:
        raise ProtectionDenied("CONTRACT_ATTESTATION_DENIED")
    version, payload, sig = attestation["version"], attestation["payload"], attestation["signature"]
    if version != CONTRACT_VERSION or not isinstance(payload, dict) or not isinstance(sig, str):
        raise ProtectionDenied("CONTRACT_ATTESTATION_DENIED")
    expected = _mac({"version": version, "payload": payload}, key)
    if not hmac.compare_digest(expected, sig):
        raise ProtectionDenied("CONTRACT_ATTESTATION_DENIED")
    if "authenticated" in payload:
        raise ProtectionDenied("CONTRACT_ATTESTATION_DENIED")
    return dict(payload)


def issue_protected_view(record: dict[str, Any], attestation: dict[str, Any],
                         principal: Principal, *, purpose: str, destination: str,
                         registry_key: bytes, release_key: bytes,
                         policy_authority: PolicyRegistry,
                         now: int | None = None, ttl_seconds: int = 60) -> dict[str, Any]:
    """Trusted service only. Principal must already be authenticated externally."""
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
        raise ProtectionDenied("INVALID_TTL")
    if type(now) is not int and now is not None:
        raise ProtectionDenied("INVALID_TIME")
    contract = _verify_contract(attestation, registry_key)
    # Signed policy identity and current version must match trusted registry state.
    policy_id, policy_version = contract.get("policy_id"), contract.get("policy_version")
    if (not isinstance(policy_id, str) or not policy_id
        or type(policy_version) is not int or policy_version < 1):
        raise ProtectionDenied("INVALID_POLICY_VERSION")
    if contract.get("tenant") != principal.tenant:
        raise ProtectionDenied("UNVERIFIED_CONTRACT")
    policy_authority.require_active(tenant=principal.tenant, policy_id=policy_id,
                                    version=policy_version)
    # Authentication is derived from verified signature, NEVER from caller data.
    contract["authenticated"] = True
    safe = protect(record, contract, principal, purpose=purpose, destination=destination)
    issued = int(time.time()) if now is None else now
    receipt = {"version": RECEIPT_VERSION, "subject": principal.subject,
               "tenant": principal.tenant, "purpose": purpose,
               "audience": destination, "operation": "read",
               "issued_at": issued, "expires_at": issued + ttl_seconds,
               "nonce": secrets.token_hex(16), "policy_id": policy_id,
               "policy_version": policy_version, "protected_view": safe}
    return {"receipt": receipt, "signature": _mac(receipt, release_key)}


class InMemoryReplayStore:
    """Thread-safe single-process demonstration; NOT a distributed replay store."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: dict[str, int] = {}

    def consume(self, nonce: str, expires_at: int, now: int) -> bool:
        with self._lock:
            self._seen = {n: e for n, e in self._seen.items() if e >= now}
            if nonce in self._seen:
                return False
            self._seen[nonce] = expires_at
            return True


def verify_protected_release(envelope: dict[str, Any], principal: Principal, *,
                             destination: str, purpose: str, release_key: bytes,
                             replay_store: ReplayLedger,
                             policy_authority: PolicyRegistry,
                             now: int | None = None,
                             operation: str = "read") -> dict[str, Any]:
    """Verify signed, time-bounded, one-use reference-only release.

    Must run inside a trusted service. No detokenization or network side effect.
    """
    if not isinstance(envelope, dict) or set(envelope) != {"receipt", "signature"}:
        raise ProtectionDenied("RELEASE_ATTESTATION_DENIED")
    receipt, sig = envelope["receipt"], envelope["signature"]
    if not isinstance(receipt, dict) or not isinstance(sig, str):
        raise ProtectionDenied("RELEASE_ATTESTATION_DENIED")
    if not hmac.compare_digest(_mac(receipt, release_key), sig):
        raise ProtectionDenied("RELEASE_ATTESTATION_DENIED")
    ts = int(time.time()) if now is None else now
    if type(ts) is not int:
        raise ProtectionDenied("INVALID_TIME")
    issued, expiry, nonce = receipt.get("issued_at"), receipt.get("expires_at"), receipt.get("nonce")
    if (receipt.get("version") != RECEIPT_VERSION or receipt.get("operation") != "read"
        or operation != "read" or type(issued) is not int or type(expiry) is not int
        or not isinstance(nonce, str) or len(nonce) != 32
        or issued > ts or expiry < ts or expiry - issued > 300
        or receipt.get("subject") != principal.subject
        or receipt.get("tenant") != principal.tenant
        or receipt.get("purpose") != purpose or purpose not in principal.purposes
        or receipt.get("audience") != destination):
        raise ProtectionDenied("RELEASE_POLICY_DENIED")
    # Check current policy AFTER receipt verification, BEFORE nonce consumption.
    policy_authority.require_active(tenant=principal.tenant,
                                    policy_id=receipt.get("policy_id"),
                                    version=receipt.get("policy_version"))
    view = authorize_release(receipt.get("protected_view"), principal,
                             destination=destination, purpose=purpose, operation=operation)
    if not replay_store.consume(nonce, expiry, ts):
        raise ProtectionDenied("REPLAY_DENIED")
    return view
