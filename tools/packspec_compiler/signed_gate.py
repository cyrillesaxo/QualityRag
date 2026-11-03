"""Signed-bundle entrypoint for the QualityRag unified decision gate."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from signed_bundles import verify_policy, verify_attestation
from unified_gate import guarded_generate


class SQLiteNonceStore:
    """Local durable single-writer nonce ledger; not multi-region replay consensus.

    Use a shared transactional store for horizontally scaled services.
    Keep this path on durable storage; clearing it resets replay protection.
    """
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("In-memory nonce ledger is not durable")
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("CREATE TABLE IF NOT EXISTS used_nonce (service TEXT NOT NULL, "
                       "environment TEXT NOT NULL, nonce TEXT NOT NULL, "
                       "PRIMARY KEY (service, environment, nonce))")

    def __call__(self, service: str, environment: str, nonce: str) -> bool:
        try:
            with sqlite3.connect(self.path, timeout=5, isolation_level="IMMEDIATE") as db:
                db.execute("INSERT INTO used_nonce (service, environment, nonce) VALUES (?,?,?)",
                           (service, environment, nonce))
            return True
        except sqlite3.IntegrityError:
            return False
        # IO/locking/corruption errors intentionally propagate to fail closed.


def guarded_generate_signed(
    signed_policy: dict,
    signed_observations: dict,
    *,
    policy_keys: dict[str, Ed25519PublicKey],
    attestor_keys: dict[str, Ed25519PublicKey],
    service: str,
    environment: str,
    minimum_sequence: int,
    nonce_accepted: Callable[[str, str, str], bool],
    witnesses: list[dict],
    observations: dict,
    as_of: str,
    generator: Callable[[], object],
) -> dict:
    """Verify signed policy *before* evaluating and authorize one generation.

    Policy verification failure raises (generator is never invoked).
    Attestation mismatch/replay produces INCONCLUSIVE via existing gate.
    Distinct trust maps prevent a policy signer from automatically attesting evidence.
    """
    payload = verify_policy(signed_policy, policy_keys, service=service, environment=environment,
                            as_of=as_of, minimum_sequence=minimum_sequence)

    def validate_attestation(_source, evaluated_witnesses, evaluated_observations):
        return verify_attestation(
            signed_observations, attestor_keys, policy_signature=signed_policy["signature"],
            service=service, environment=environment, as_of=as_of,
            witnesses=evaluated_witnesses, observations=evaluated_observations,
            nonce_accepted=nonce_accepted)

    response = guarded_generate(
        payload["ir"], witnesses, observations, as_of, generator,
        verify_attestation=validate_attestation)
    response["decision"]["signed_policy"] = {
        "key_id": signed_policy["key_id"], "sequence": payload["sequence"],
        "service": service, "environment": environment,
        "source_sha256": payload["ir"]["source"]["sha256"],
    }
    response["decision"]["attestation_method"] = "ED25519_SIGNED_BUNDLE"
    return response
