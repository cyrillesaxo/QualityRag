"""No-network disclosure gate: synthetic identity, signed contract and routes."""
import copy
import os
import tempfile
import unittest

from qualityrag.protection import ProtectionDenied, SCHEMA
from qualityrag.protection_attestation import attest_contract
from qualityrag.protection_disclosure import (
    DisclosureRoute, DryRunDisclosureGateway, MemoryReferenceSink,
)
from qualityrag.protection_grants import StaticWorkloadGrants, WorkloadGrant
from qualityrag.protection_service import (
    ProtectionService, SignedWorkloadVerifier, WorkloadTrust, sign_synthetic_workload,
)
from qualityrag.protection_sqlite import SQLitePolicyAuthority, SQLiteReplayStore

ID_KEY = b"disclosure-demo-identity-32-byte-key-123"
REG_KEY = b"disclosure-demo-registry-32-byte-key-123"
REL_KEY = b"disclosure-demo-release-32-byte-key-123"


class DryRunDisclosureTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        path = os.path.join(self.tempdir.name, "disclosure.sqlite")
        self.policies = SQLitePolicyAuthority(path)
        self.policies.publish(tenant="t1", policy_id="p1", version=1)
        self.verifier = SignedWorkloadVerifier(
            WorkloadTrust("issuer", "qualityrag", {"k1": ID_KEY}))
        self.service = ProtectionService(
            verifier=self.verifier, policy_authority=self.policies,
            replay_store=SQLiteReplayStore(path),
            workload_grants=StaticWorkloadGrants(
                [WorkloadGrant("t1", "operator", "review", "mock-ai")]),
            registry_key=REG_KEY, release_key=REL_KEY)
        self.assertion = sign_synthetic_workload(
            {"iss": "issuer", "aud": "qualityrag", "sub": "operator",
             "tenant": "t1", "purposes": ["review"],
             "iat": 100, "exp": 300}, kid="k1", key=ID_KEY)
        grants = [{"purpose": "review", "destination": "mock-ai", "operation": "read"}]
        self.contract = attest_contract({
            "schema": SCHEMA, "tenant": "t1", "policy_id": "p1",
            "policy_version": 1,
            "fields": {
                "payment_ref": {"classification": "pci", "mode": "reference",
                                "grants": []},
                "payment_terms": {"classification": "public", "mode": "plain",
                                  "grants": grants},
            },
        }, REG_KEY)
        self.sink = MemoryReferenceSink()
        self.gateway = DryRunDisclosureGateway(
            service=self.service, routes=[DisclosureRoute("mock-ai", self.sink)])

    def issue(self):
        return self.service.issue(
            assertion=self.assertion,
            record={"payment_ref": "ref_example_payment_00001",
                    "payment_terms": "Due in 30 days"},
            contract_attestation=self.contract, purpose="review",
            destination="mock-ai", now=150)

    def deliver(self, envelope, *, destination="mock-ai", assertion=None):
        return self.gateway.deliver(
            assertion=self.assertion if assertion is None else assertion,
            envelope=envelope, purpose="review",
            destination=destination, now=151)

    def test_only_approved_view_reaches_sink(self):
        result = self.deliver(self.issue())
        self.assertEqual(result["status"], "SIMULATED_DELIVERY_ACCEPTED")
        self.assertEqual(self.sink.received, [{"payment_terms": "Due in 30 days"}])

    def test_wrong_route_fails_before_any_sink_call(self):
        env = self.issue()
        with self.assertRaisesRegex(ProtectionDenied, "DESTINATION_NOT_CONFIGURED"):
            self.deliver(env, destination="https://attacker.example")
        self.assertEqual(self.sink.received, [])
        # A denied, unconfigured destination does not consume the receipt.
        self.deliver(env)
        self.assertEqual(len(self.sink.received), 1)

    def test_receipt_replay_denied_without_second_delivery(self):
        env = self.issue()
        self.deliver(env)
        with self.assertRaisesRegex(ProtectionDenied, "REPLAY_DENIED"):
            self.deliver(env)
        self.assertEqual(len(self.sink.received), 1)

    def test_revocation_between_issuance_and_delivery(self):
        env = self.issue()
        self.policies.revoke(tenant="t1", policy_id="p1")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.deliver(env)
        self.assertEqual(self.sink.received, [])

    def test_forged_destination_in_receipt(self):
        env = self.issue()
        forged = copy.deepcopy(env)
        forged["receipt"]["audience"] = "other"
        with self.assertRaisesRegex(ProtectionDenied, "RELEASE_ATTESTATION_DENIED"):
            self.deliver(forged)
        self.assertEqual(self.sink.received, [])

    def test_denied_identity_never_calls_sink(self):
        env = self.issue()
        forged = copy.deepcopy(self.assertion)
        forged["claims"]["sub"] = "someone-else"
        with self.assertRaisesRegex(ProtectionDenied, "IDENTITY_DENIED"):
            self.deliver(env, assertion=forged)
        self.assertEqual(self.sink.received, [])

    def test_sink_failure_consumes_authorization_and_is_not_retried(self):
        class BrokenSink:
            def __init__(self):
                self.calls = 0
            def accept(self, view):
                self.calls += 1
                raise RuntimeError("do not expose sink details")
        broken = BrokenSink()
        gateway = DryRunDisclosureGateway(
            service=self.service, routes=[DisclosureRoute("mock-ai", broken)])
        env = self.issue()
        with self.assertRaisesRegex(ProtectionDenied, "SIMULATED_DELIVERY_FAILED"):
            gateway.deliver(assertion=self.assertion, envelope=env, purpose="review",
                            destination="mock-ai", now=151)
        with self.assertRaisesRegex(ProtectionDenied, "REPLAY_DENIED"):
            gateway.deliver(assertion=self.assertion, envelope=env, purpose="review",
                            destination="mock-ai", now=151)
        self.assertEqual(broken.calls, 1)

    def test_duplicate_routes_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "DUPLICATE_DESTINATION"):
            DryRunDisclosureGateway(
                service=self.service,
                routes=[DisclosureRoute("mock-ai", self.sink),
                        DisclosureRoute("mock-ai", MemoryReferenceSink())])


if __name__ == "__main__":
    unittest.main()
