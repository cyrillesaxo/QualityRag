"""Metadata provenance and object-level access synthetic regression suite."""
import copy
import unittest

from qualityrag.protection import ProtectionDenied, SCHEMA
from qualityrag.protection_attestation import InMemoryReplayStore, attest_contract
from qualityrag.protection_grants import StaticWorkloadGrants, WorkloadGrant
from qualityrag.protection_lifecycle import InMemoryPolicyAuthority
from qualityrag.protected_metadata import (
    ProtectedPayment, SyntheticAuthorizedMetadataProvider,
)
from qualityrag.protection_service import (
    ProtectionService, SignedWorkloadVerifier, WorkloadTrust,
    sign_synthetic_workload,
)

WORKLOAD_KEY = b"provenance-fixture-identity-key-32-byte"
REGISTRY_KEY = b"provenance-fixture-registry-key-32-byte"
RELEASE_KEY = b"provenance-fixture-release-key-32-byte"
REFERENCE = "ref_source_owned_payment_00001"


class MetadataProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.policy = InMemoryPolicyAuthority()
        self.policy.publish(tenant="tenant-a", policy_id="payment", version=1)
        self.principal_claims = {
            "iss": "issuer", "aud": "protect", "sub": "worker-a",
            "tenant": "tenant-a", "purposes": ["review"], "iat": 1000,
            "exp": 1100,
        }
        self.assertion = self.sign(self.principal_claims)
        self.payments = [
            ProtectedPayment(REFERENCE, "tenant-a", "visa", "4242", True),
        ]
        self.provider = SyntheticAuthorizedMetadataProvider(
            self.payments, {("tenant-a", REFERENCE): {("worker-a", "review")}})
        self.grants = StaticWorkloadGrants([
            WorkloadGrant("tenant-a", "worker-a", "review", "llm"),
            WorkloadGrant("tenant-a", "worker-b", "review", "llm"),
        ])
        self.service = self.service_with(self.provider)
        grant = [{"purpose": "review", "destination": "llm", "operation": "read"}]
        self.attestation = attest_contract({
            "schema": SCHEMA, "tenant": "tenant-a",
            "policy_id": "payment", "policy_version": 1,
            "fields": {
                "payment_ref": {"classification": "pci", "mode": "reference", "grants": []},
                "card_brand": {"classification": "pci", "mode": "derived", "grants": []},
                "last_four": {"classification": "pci", "mode": "derived", "grants": []},
                "expiry_valid": {"classification": "pci", "mode": "derived", "grants": grant},
            },
        }, REGISTRY_KEY)

    def sign(self, claims):
        return sign_synthetic_workload(
            claims, kid="k", key=WORKLOAD_KEY)

    def service_with(self, provider):
        return ProtectionService(
            verifier=SignedWorkloadVerifier(
                WorkloadTrust("issuer", "protect", {"k": WORKLOAD_KEY})),
            workload_grants=self.grants, metadata_provider=provider,
            policy_authority=self.policy, replay_store=InMemoryReplayStore(),
            registry_key=REGISTRY_KEY, release_key=RELEASE_KEY)

    def issue(self, *, assertion=None, reference=REFERENCE, service=None):
        return (service or self.service).issue_payment_metadata(
            assertion=self.assertion if assertion is None else assertion,
            payment_reference=reference, contract_attestation=self.attestation,
            purpose="review", destination="llm", now=1001)

    def test_only_source_owned_and_permitted_attribute_is_released(self):
        envelope = self.issue()
        self.assertEqual(envelope["receipt"]["protected_view"]["view"],
                         {"expiry_valid": True})
        decision = self.service.release(
            assertion=self.assertion, envelope=envelope,
            purpose="review", destination="llm", now=1002)
        self.assertEqual(decision["view"], {"expiry_valid": True})

    def test_unauthorized_object_denied_despite_valid_signed_workload(self):
        other = self.sign({**self.principal_claims, "sub": "worker-b"})
        with self.assertRaisesRegex(ProtectionDenied, "METADATA_ACCESS_DENIED"):
            self.issue(assertion=other)

    def test_cross_tenant_metadata_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "WORKLOAD_NOT_AUTHORIZED"):
            other = self.sign({**self.principal_claims, "tenant": "tenant-b"})
            self.issue(assertion=other)

    def test_unknown_reference_denied(self):
        with self.assertRaises(ProtectionDenied):
            self.issue(reference="ref_other_payment_00000001")

    def test_missing_provider_fails_closed(self):
        with self.assertRaisesRegex(ProtectionDenied, "METADATA_PROVIDER_UNAVAILABLE"):
            self.issue(service=self.service_with(None))

    def test_source_tenant_reference_mismatch_denied(self):
        class CompromisedProvider:
            def get_authorized_payment(self, **kwargs):
                return ProtectedPayment("ref_wrong_reference_000001",
                                        "tenant-a", "visa", "4444", True)
        with self.assertRaisesRegex(ProtectionDenied, "METADATA_SOURCE_MISMATCH"):
            self.issue(service=self.service_with(CompromisedProvider()))

    def test_unverified_untrusted_attribute_overrides_not_accepted(self):
        # Caller controls only reference, not card metadata.
        envelope = self.issue()
        self.assertNotIn("payment_terms",
                         envelope["receipt"]["protected_view"]["view"])

    def test_attestation_tampering_fails_closed(self):
        self.attestation = copy.deepcopy(self.attestation)
        self.attestation["payload"]["fields"]["last_four"]["grants"] = [
            {"purpose": "review", "destination": "llm", "operation": "read"}]
        with self.assertRaisesRegex(ProtectionDenied, "CONTRACT_ATTESTATION_DENIED"):
            self.issue()


if __name__ == "__main__":
    unittest.main()
