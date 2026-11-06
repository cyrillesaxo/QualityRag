"""End-to-end synthetic service test with durable policy and replay stores."""
import os
import tempfile
import unittest

from qualityrag.protection import ProtectionDenied, SCHEMA
from qualityrag.protection_attestation import attest_contract
from qualityrag.protection_grants import StaticWorkloadGrants, WorkloadGrant
from qualityrag.protection_service import (
    ProtectionService, SignedWorkloadVerifier, WorkloadTrust, sign_synthetic_workload,
)
from qualityrag.protection_sqlite import SQLitePolicyAuthority, SQLiteReplayStore


KEY_IDENTITY = b"synthetic-test-identity-key-32-byte-minimum"
KEY_REGISTRY = b"synthetic-test-registry-key-32-byte-minimum"
KEY_RELEASE = b"synthetic-test-release-key-32-byte-minimum"


class DurableServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "persistent-protect.db")
        self.authority = SQLitePolicyAuthority(self.path)
        self.authority.publish(tenant="one", policy_id="p", version=1)
        self.verifier = SignedWorkloadVerifier(
            WorkloadTrust("issuer", "protect", {"active": KEY_IDENTITY}))
        self.grants = StaticWorkloadGrants([
            WorkloadGrant("one", "reader", "review", "model")])
        self.assertion = sign_synthetic_workload(
            {"iss": "issuer", "aud": "protect", "sub": "reader",
             "tenant": "one", "purposes": ["review"], "iat": 100, "exp": 300},
            kid="active", key=KEY_IDENTITY)
        grant = [{"purpose": "review", "destination": "model", "operation": "read"}]
        self.attestation = attest_contract(
            {"schema": SCHEMA, "tenant": "one", "policy_id": "p",
             "policy_version": 1,
             "fields": {"terms": {"classification": "public",
                                  "mode": "plain", "grants": grant}}},
            KEY_REGISTRY)

    def service(self):
        return ProtectionService(
            verifier=self.verifier, workload_grants=self.grants,
            policy_authority=SQLitePolicyAuthority(self.path),
            replay_store=SQLiteReplayStore(self.path),
            registry_key=KEY_REGISTRY, release_key=KEY_RELEASE)

    def issue(self):
        return self.service().issue(
            assertion=self.assertion, record={"terms": "Due in thirty days"},
            contract_attestation=self.attestation, purpose="review",
            destination="model", now=150)

    def release(self, env):
        return self.service().release(
            assertion=self.assertion, envelope=env, purpose="review",
            destination="model", now=151)

    def test_release_survives_restart_but_cannot_replay(self):
        env = self.issue()
        self.assertEqual(self.release(env)["view"], {"terms": "Due in thirty days"})
        with self.assertRaisesRegex(ProtectionDenied, "REPLAY_DENIED"):
            self.release(env)

    def test_revocation_survives_restart_and_blocks_release(self):
        env = self.issue()
        self.authority.revoke(tenant="one", policy_id="p")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.release(env)
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.issue()


if __name__ == "__main__":
    unittest.main()
