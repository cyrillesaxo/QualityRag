import copy
import unittest

from qualityrag.protection import ProtectionDenied, SCHEMA
from qualityrag.protection_attestation import attest_contract, InMemoryReplayStore
from qualityrag.protection_lifecycle import InMemoryPolicyAuthority
from qualityrag.protection_grants import StaticWorkloadGrants, WorkloadGrant
from qualityrag.protection_service import (
    WorkloadTrust, SignedWorkloadVerifier, ProtectionService, sign_synthetic_workload,
)

WORKLOAD_KEY = b"synthetic-test-workload-key-minimum-32-bytes"
REGISTRY_KEY = b"synthetic-test-registry-key-minimum-32-bytes"
RELEASE_KEY = b"synthetic-test-release-key-minimum-32-bytes"


class ProtectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.trust = WorkloadTrust("demo-issuer", "qualityrag-protect",
                                   {"key-1": WORKLOAD_KEY})
        self.verifier = SignedWorkloadVerifier(self.trust)
        self.policies = InMemoryPolicyAuthority()
        self.policies.publish(tenant="tenant-a", policy_id="payment", version=1)
        self.grants = StaticWorkloadGrants([
            WorkloadGrant("tenant-a", "worker-a", "review", "llm")
        ])
        self.service = ProtectionService(
            workload_grants=self.grants,
            verifier=self.verifier, policy_authority=self.policies,
            replay_store=InMemoryReplayStore(), registry_key=REGISTRY_KEY,
            release_key=RELEASE_KEY)
        self.claims = {"iss": "demo-issuer", "aud": "qualityrag-protect",
                       "sub": "worker-a", "tenant": "tenant-a",
                       "purposes": ["review"], "iat": 1000, "exp": 1100}
        self.assertion = self.sign(self.claims)
        self.record = {"payment_ref": "ref_example_payment_00001",
                       "due_terms": "Payment due in 30 days"}
        grant = [{"purpose": "review", "destination": "llm", "operation": "read"}]
        self.contract = {
            "schema": SCHEMA, "tenant": "tenant-a", "policy_id": "payment",
            "policy_version": 1,
            "fields": {
                "payment_ref": {"classification": "pci", "mode": "reference", "grants": grant},
                "due_terms": {"classification": "public", "mode": "plain", "grants": grant},
            },
        }
        self.attested = attest_contract(self.contract, REGISTRY_KEY)

    def sign(self, claims):
        return sign_synthetic_workload(claims, kid="key-1", key=WORKLOAD_KEY)

    def issue(self, assertion=None):
        return self.service.issue(
            assertion=self.assertion if assertion is None else assertion,
            record=self.record, contract_attestation=self.attested,
            purpose="review", destination="llm", now=1001)

    def release(self, envelope, assertion=None):
        return self.service.release(
            assertion=self.assertion if assertion is None else assertion,
            envelope=envelope, purpose="review", destination="llm", now=1002)

    def test_verified_workload_can_issue_and_release(self):
        envelope = self.issue()
        self.assertEqual(self.release(envelope)["view"], self.record)

    def test_modified_subject_denied(self):
        forged = copy.deepcopy(self.assertion)
        forged["claims"]["sub"] = "attacker"
        with self.assertRaisesRegex(ProtectionDenied, "IDENTITY_DENIED"):
            self.issue(forged)

    def test_wrong_audience_denied(self):
        claims = dict(self.claims, aud="other-service")
        with self.assertRaisesRegex(ProtectionDenied, "IDENTITY_DENIED"):
            self.issue(self.sign(claims))

    def test_expired_assertion_denied(self):
        claims = dict(self.claims, exp=1001)
        with self.assertRaisesRegex(ProtectionDenied, "IDENTITY_DENIED"):
            self.issue(self.sign(claims))

    def test_wrong_tenant_cannot_use_signed_contract(self):
        claims = dict(self.claims, tenant="tenant-b")
        with self.assertRaisesRegex(ProtectionDenied, "WORKLOAD_NOT_AUTHORIZED"):
            self.issue(self.sign(claims))

    def test_wrong_subject_cannot_release(self):
        envelope = self.issue()
        other = self.sign(dict(self.claims, sub="other-worker"))
        with self.assertRaises(ProtectionDenied):
            self.release(envelope, assertion=other)

    def test_untrusted_key_id_denied(self):
        wrong = copy.deepcopy(self.assertion)
        wrong["kid"] = "unknown"
        with self.assertRaisesRegex(ProtectionDenied, "IDENTITY_DENIED"):
            self.issue(wrong)

    def test_signed_but_unapproved_workload_denied(self):
        claims = dict(self.claims, sub="unapproved-worker")
        with self.assertRaisesRegex(ProtectionDenied, "WORKLOAD_NOT_AUTHORIZED"):
            self.issue(self.sign(claims))

    def test_signed_expanded_purpose_denied_by_service(self):
        claims = dict(self.claims, purposes=["review", "export"])
        with self.assertRaisesRegex(ProtectionDenied, "WORKLOAD_NOT_AUTHORIZED"):
            self.service.issue(
                assertion=self.sign(claims), record=self.record,
                contract_attestation=self.attested,
                purpose="export", destination="llm", now=1001)

    def test_signed_worker_cannot_change_destination(self):
        with self.assertRaisesRegex(ProtectionDenied, "WORKLOAD_NOT_AUTHORIZED"):
            self.service.issue(
                assertion=self.assertion, record=self.record,
                contract_attestation=self.attested,
                purpose="review", destination="attacker", now=1001)

    def test_revocation_after_issuance_denied(self):
        envelope = self.issue()
        self.policies.revoke(tenant="tenant-a", policy_id="payment")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.release(envelope)

    def test_replay_denied(self):
        envelope = self.issue()
        self.release(envelope)
        with self.assertRaisesRegex(ProtectionDenied, "REPLAY_DENIED"):
            self.release(envelope)


if __name__ == "__main__":
    unittest.main()
