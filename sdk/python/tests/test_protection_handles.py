"""Synthetic tests: opaque handles never expose internal signed receipts."""
import os
import tempfile
import unittest

from qualityrag.protection import ProtectionDenied, SCHEMA
from qualityrag.protection_attestation import attest_contract
from qualityrag.protection_disclosure import (
    DisclosureRoute, DryRunDisclosureGateway, MemoryReferenceSink,
)
from qualityrag.protection_grants import StaticWorkloadGrants, WorkloadGrant
from qualityrag.protection_handles import InMemoryReceiptRegistry, OpaqueDisclosureFacade
from qualityrag.protected_metadata import (
    ProtectedPayment, SyntheticAuthorizedMetadataProvider,
)
from qualityrag.protection_service import (
    ProtectionService, SignedWorkloadVerifier, WorkloadTrust,
    sign_synthetic_workload,
)
from qualityrag.protection_sqlite import SQLitePolicyAuthority, SQLiteReplayStore

IDENTITY_KEY = b"synthetic-opaque-id-key-32-bytes-long!"
REGISTRY_KEY = b"synthetic-opaque-registry-key-32bytes"
RELEASE_KEY = b"synthetic-opaque-release-key-32bytes"
REFERENCE = "ref_synthetic_opaque_payment_00001"


class OpaqueHandleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = os.path.join(self.tmp.name, "opaque.db")
        self.policies = SQLitePolicyAuthority(path)
        self.policies.publish(tenant="tenant1", policy_id="payment", version=1)
        self.provider = SyntheticAuthorizedMetadataProvider(
            [ProtectedPayment(REFERENCE, "tenant1", "visa", "4242", True)],
            {("tenant1", REFERENCE): {("operator", "review")}})
        self.service = ProtectionService(
            verifier=SignedWorkloadVerifier(
                WorkloadTrust("issuer", "protect", {"k1": IDENTITY_KEY})),
            workload_grants=StaticWorkloadGrants(
                [WorkloadGrant("tenant1", "operator", "review", "model")]),
            metadata_provider=self.provider,
            policy_authority=self.policies,
            replay_store=SQLiteReplayStore(path),
            registry_key=REGISTRY_KEY, release_key=RELEASE_KEY)
        self.assertion = sign_synthetic_workload(
            {"iss": "issuer", "aud": "protect", "sub": "operator",
             "tenant": "tenant1", "purposes": ["review"],
             "iat": 100, "exp": 250}, kid="k1", key=IDENTITY_KEY)
        grant = [{"purpose": "review", "destination": "model", "operation": "read"}]
        self.contract = attest_contract({
            "schema": SCHEMA, "tenant": "tenant1",
            "policy_id": "payment", "policy_version": 1,
            "fields": {
                "payment_ref": {"classification": "pci", "mode": "reference", "grants": []},
                "card_brand": {"classification": "pci", "mode": "derived", "grants": []},
                "last_four": {"classification": "pci", "mode": "derived", "grants": []},
                "expiry_valid": {"classification": "pci", "mode": "derived", "grants": grant},
            },
        }, REGISTRY_KEY)
        self.sink = MemoryReferenceSink()
        self.registry = InMemoryReceiptRegistry(max_pending=2)
        self.gateway = DryRunDisclosureGateway(
            service=self.service, routes=[DisclosureRoute("model", self.sink)])
        self.facade = OpaqueDisclosureFacade(
            service=self.service, gateway=self.gateway, registry=self.registry)

    def prepare(self):
        return self.facade.prepare_payment(
            assertion=self.assertion, payment_reference=REFERENCE,
            contract_attestation=self.contract, purpose="review",
            destination="model", now=150)

    def deliver(self, handle, *, assertion=None, destination="model", now=151):
        return self.facade.deliver(
            assertion=self.assertion if assertion is None else assertion,
            request_handle=handle, purpose="review", destination=destination,
            now=now)

    def test_public_response_excludes_internal_receipt(self):
        response = self.prepare()
        self.assertEqual(set(response), {"request_handle", "view"})
        self.assertEqual(response["view"], {"expiry_valid": True})
        self.assertTrue(response["request_handle"].startswith("req_"))
        self.assertNotIn(REFERENCE, str(response))
        self.assertNotIn("signature", str(response))
        self.assertNotIn("nonce", str(response))
        self.assertNotIn("policy_version", str(response))

    def test_deliver_once_then_handle_discarded(self):
        response = self.prepare()
        self.assertEqual(self.deliver(response["request_handle"])["status"],
                         "SIMULATED_DELIVERY_ACCEPTED")
        self.assertEqual(self.sink.received, [{"expiry_valid": True}])
        with self.assertRaisesRegex(ProtectionDenied, "UNKNOWN_REQUEST"):
            self.deliver(response["request_handle"])

    def test_unknown_handle_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "UNKNOWN_REQUEST"):
            self.deliver("req_not_real")

    def test_wrong_destination_denied_without_consuming_handle(self):
        handle = self.prepare()["request_handle"]
        with self.assertRaisesRegex(ProtectionDenied, "DESTINATION_NOT_CONFIGURED"):
            self.deliver(handle, destination="attacker")
        self.assertEqual(self.sink.received, [])
        self.deliver(handle)
        self.assertEqual(len(self.sink.received), 1)

    def test_source_revocation_denies_prepared_receipt(self):
        handle = self.prepare()["request_handle"]
        self.provider.revoke_synthetic_access(
            tenant="tenant1", reference=REFERENCE,
            subject="operator", purpose="review")
        with self.assertRaisesRegex(ProtectionDenied, "METADATA_ACCESS_DENIED"):
            self.deliver(handle)
        self.assertEqual(self.sink.received, [])

    def test_policy_revocation_denies_prepared_receipt(self):
        handle = self.prepare()["request_handle"]
        self.policies.revoke(tenant="tenant1", policy_id="payment")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.deliver(handle)
        self.assertEqual(self.sink.received, [])

    def test_signed_identity_must_still_match(self):
        handle = self.prepare()["request_handle"]
        fake = dict(self.assertion)
        fake["signature"] = "0" * 64
        with self.assertRaisesRegex(ProtectionDenied, "IDENTITY_DENIED"):
            self.deliver(handle, assertion=fake)
        self.assertEqual(self.sink.received, [])

    def test_bounded_registry(self):
        self.prepare()
        self.prepare()
        with self.assertRaisesRegex(ProtectionDenied, "RECEIPT_CAPACITY_REACHED"):
            self.prepare()

    def test_expired_handle_denied(self):
        handle = self.prepare()["request_handle"]
        with self.assertRaisesRegex(ProtectionDenied, "UNKNOWN_REQUEST"):
            self.deliver(handle, now=211)


if __name__ == "__main__":
    unittest.main()
