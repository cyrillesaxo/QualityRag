import copy
import unittest

from qualityrag.protection import Principal, ProtectionDenied, SCHEMA
from qualityrag.protection_attestation import (
    attest_contract, issue_protected_view, verify_protected_release, InMemoryReplayStore,
)

REGISTRY_KEY = b"registry-secret-test-key-32-bytes-minimum!"
RELEASE_KEY = b"release-secret-test-key-32-bytes-minimum!"


class AttestedProtectionTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("operator", "tenant1", frozenset({"review"}))
        grant = [{"purpose": "review", "destination": "llm", "operation": "read"}]
        self.contract = {"schema": SCHEMA, "tenant": "tenant1", "authenticated": False,
                         "fields": {
                             "payment_ref": {"classification": "pci", "mode": "reference", "grants": grant},
                             "last_four": {"classification": "pci", "mode": "derived", "grants": grant},
                             "due_terms": {"classification": "public", "mode": "plain", "grants": grant},
                         }}
        self.record = {"payment_ref": "ref_abc_def_0123456789",
                       "last_four": "4242", "due_terms": "Payment due in 30 days"}
        self.attested = attest_contract(self.contract, REGISTRY_KEY)
        self.replay = InMemoryReplayStore()

    def issue(self, attestation=None, record=None):
        return issue_protected_view(
            self.record if record is None else record,
            self.attested if attestation is None else attestation, self.principal,
            purpose="review", destination="llm", registry_key=REGISTRY_KEY,
            release_key=RELEASE_KEY, now=1000, ttl_seconds=60)

    def release(self, envelope, **kwargs):
        return verify_protected_release(
            envelope, self.principal, destination="llm", purpose="review",
            release_key=RELEASE_KEY, replay_store=self.replay,
            now=kwargs.get("now", 1001), operation=kwargs.get("operation", "read"))

    def test_signed_contract_and_one_use_release(self):
        envelope = self.issue()
        self.assertEqual(self.release(envelope)["view"], self.record)
        with self.assertRaisesRegex(ProtectionDenied, "REPLAY_DENIED"):
            self.release(envelope)

    def test_tampered_contract_is_denied(self):
        tampered = copy.deepcopy(self.attested)
        tampered["payload"]["fields"]["payment_ref"]["mode"] = "plain"
        with self.assertRaisesRegex(ProtectionDenied, "CONTRACT_ATTESTATION_DENIED"):
            self.issue(attestation=tampered)

    def test_caller_claims_do_not_bypass_attestation(self):
        unsigned = {"version": "qualityrag.contract-attestation/v0.1",
                    "payload": {**self.contract, "authenticated": True}, "signature": "fake"}
        with self.assertRaises(ProtectionDenied):
            self.issue(attestation=unsigned)

    def test_forged_receipt_rejected(self):
        envelope = self.issue()
        envelope["receipt"]["protected_view"]["view"]["payment_ref"] = "ref_attacker_controlled"
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_ATTESTATION_DENIED"):
            self.release(envelope)

    def test_wrong_receipt_signing_key_denied(self):
        envelope = self.issue()
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_ATTESTATION_DENIED"):
            verify_protected_release(envelope, self.principal, destination="llm",
                                     purpose="review", release_key=REGISTRY_KEY,
                                     replay_store=self.replay, now=1001)

    def test_expired_receipt_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_POLICY_DENIED"):
            self.release(self.issue(), now=1061)

    def test_future_receipt_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_POLICY_DENIED"):
            self.release(self.issue(), now=999)

    def test_operation_escalation_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_POLICY_DENIED"):
            self.release(self.issue(), operation="detokenize")

    def test_raw_pan_denied(self):
        record = dict(self.record, payment_ref="4111111111111111")
        with self.assertRaisesRegex(ProtectionDenied, "UNSAFE_REFERENCE"):
            self.issue(record=record)

    def test_cross_tenant_denied(self):
        wrong = Principal("operator", "tenant2", frozenset({"review"}))
        with self.assertRaises(ProtectionDenied):
            issue_protected_view(self.record, self.attested, wrong, purpose="review",
                                 destination="llm", registry_key=REGISTRY_KEY,
                                 release_key=RELEASE_KEY, now=1000)

    def test_wrong_audience_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_POLICY_DENIED"):
            verify_protected_release(self.issue(), self.principal, destination="attacker",
                                     purpose="review", release_key=RELEASE_KEY,
                                     replay_store=self.replay, now=1001)

    def test_invalid_ttl_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "INVALID_TTL"):
            issue_protected_view(self.record, self.attested, self.principal,
                                 purpose="review", destination="llm",
                                 registry_key=REGISTRY_KEY, release_key=RELEASE_KEY,
                                 now=1000, ttl_seconds=3600)


if __name__ == "__main__":
    unittest.main()
