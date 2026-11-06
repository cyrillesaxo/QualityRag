"""Experimental trusted-workload boundary for QualityRAG protection.

Authentication adapter accepts a signed workload assertion as a *demonstration*
only. Production MUST validate an IdP's issuer, audience, token signature,
workload identity, revocation and transport-level authentication; keys stay in
the trusted service, never in models or untrusted agents.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from .protection import Principal, ProtectionDenied
from .protection_attestation import (
    InMemoryReplayStore, issue_protected_view, verify_protected_release,
)
from .protection_lifecycle import InMemoryPolicyAuthority
from .protection_grants import StaticWorkloadGrants


def _canonical(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProtectionDenied("INVALID_ASSERTION") from exc


@dataclass(frozen=True)
class WorkloadTrust:
    issuer: str
    audience: str
    keys: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if not self.issuer or not self.audience or not self.keys:
            raise ProtectionDenied("INVALID_TRUST_CONFIGURATION")
        if any(not isinstance(k, str) or not k or not isinstance(v, bytes) or len(v) < 32
               for k, v in self.keys.items()):
            raise ProtectionDenied("INVALID_TRUST_CONFIGURATION")


class SignedWorkloadVerifier:
    """Demonstration of externally authenticated principal derivation.

    This is not OAuth/OIDC/JWT verification; real deployment must replace it
    with a trusted identity provider integration.
    """

    def __init__(self, trust: WorkloadTrust) -> None:
        self._trust = trust

    def verify(self, assertion: dict[str, Any], *, now: int | None = None) -> Principal:
        if not isinstance(assertion, dict) or set(assertion) != {"kid", "claims", "signature"}:
            raise ProtectionDenied("IDENTITY_DENIED")
        kid, claims, signature = assertion["kid"], assertion["claims"], assertion["signature"]
        if not isinstance(kid, str) or not isinstance(claims, dict) or not isinstance(signature, str):
            raise ProtectionDenied("IDENTITY_DENIED")
        key = self._trust.keys.get(kid)
        if key is None:
            raise ProtectionDenied("IDENTITY_DENIED")
        expected = hmac.new(key, _canonical({"kid": kid, "claims": claims}), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ProtectionDenied("IDENTITY_DENIED")
        ts = int(time.time()) if now is None else now
        iat, exp = claims.get("iat"), claims.get("exp")
        purposes = claims.get("purposes")
        if (type(ts) is not int or type(iat) is not int or type(exp) is not int
            or iat > ts or exp <= ts or exp - iat > 300
            or claims.get("iss") != self._trust.issuer
            or claims.get("aud") != self._trust.audience
            or not isinstance(purposes, list)
            or not purposes or not all(isinstance(x, str) and x for x in purposes)
            or not isinstance(claims.get("sub"), str) or not claims.get("sub")
            or not isinstance(claims.get("tenant"), str) or not claims.get("tenant")):
            raise ProtectionDenied("IDENTITY_DENIED")
        return Principal(claims["sub"], claims["tenant"], frozenset(purposes))


def sign_synthetic_workload(claims: dict[str, Any], *, kid: str, key: bytes) -> dict[str, Any]:
    """Fixture helper: MUST NOT be exposed as a model-facing endpoint."""
    if not isinstance(key, bytes) or len(key) < 32:
        raise ProtectionDenied("INVALID_KEY")
    return {"kid": kid, "claims": claims,
            "signature": hmac.new(key, _canonical({"kid": kid, "claims": claims}),
                                  hashlib.sha256).hexdigest()}


class ProtectionService:
    """Key and principal isolation in a trusted-process example.

    The caller supplies an identity *assertion*, never an authoritative
    Principal. All operations are side-effect-free other than consuming a nonce.
    Do not expose this as a network service without independent authentication,
    hardened secret storage and distributed policy/replay enforcement.
    """

    def __init__(self, *, verifier: SignedWorkloadVerifier,
                 policy_authority: InMemoryPolicyAuthority,
                 replay_store: InMemoryReplayStore,
                 workload_grants: StaticWorkloadGrants,
                 registry_key: bytes, release_key: bytes) -> None:
        if not isinstance(registry_key, bytes) or len(registry_key) < 32:
            raise ProtectionDenied("INVALID_KEY")
        if not isinstance(release_key, bytes) or len(release_key) < 32:
            raise ProtectionDenied("INVALID_KEY")
        self._verifier = verifier
        self._policy_authority = policy_authority
        if not isinstance(workload_grants, StaticWorkloadGrants):
            raise ProtectionDenied("MISSING_WORKLOAD_GRANTS")
        self._workload_grants = workload_grants
        self._replay_store = replay_store
        self._registry_key = registry_key
        self._release_key = release_key

    def issue(self, *, assertion: dict[str, Any], record: dict[str, Any],
              contract_attestation: dict[str, Any], purpose: str,
              destination: str, now: int | None = None) -> dict[str, Any]:
        principal = self._verifier.verify(assertion, now=now)
        self._workload_grants.require(principal, purpose=purpose, destination=destination)
        return issue_protected_view(
            record, contract_attestation, principal, purpose=purpose,
            destination=destination, registry_key=self._registry_key,
            release_key=self._release_key, policy_authority=self._policy_authority,
            now=now)

    def release(self, *, assertion: dict[str, Any], envelope: dict[str, Any],
                purpose: str, destination: str, now: int | None = None) -> dict[str, Any]:
        principal = self._verifier.verify(assertion, now=now)
        self._workload_grants.require(principal, purpose=purpose, destination=destination)
        return verify_protected_release(
            envelope, principal, purpose=purpose, destination=destination,
            release_key=self._release_key, policy_authority=self._policy_authority,
            replay_store=self._replay_store, now=now)
