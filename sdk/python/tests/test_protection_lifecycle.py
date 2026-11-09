import unittest

from qualityrag.protection import ProtectionDenied
from qualityrag.protection_lifecycle import InMemoryPolicyAuthority


class PolicyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.authority = InMemoryPolicyAuthority()
        self.authority.publish(tenant="tenant-a", policy_id="p", version=1)

    def test_active_policy(self):
        self.authority.require_active(tenant="tenant-a", policy_id="p", version=1)

    def test_revoke_denies(self):
        self.authority.revoke(tenant="tenant-a", policy_id="p")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.authority.require_active(tenant="tenant-a", policy_id="p", version=1)

    def test_old_version_cannot_be_reintroduced_after_revocation(self):
        self.authority.revoke(tenant="tenant-a", policy_id="p")
        with self.assertRaisesRegex(ProtectionDenied, "NON_MONOTONIC_POLICY_VERSION"):
            self.authority.publish(tenant="tenant-a", policy_id="p", version=1)
        self.authority.publish(tenant="tenant-a", policy_id="p", version=2)
        self.authority.require_active(tenant="tenant-a", policy_id="p", version=2)

    def test_tenant_separation(self):
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            self.authority.require_active(tenant="tenant-b", policy_id="p", version=1)

    def test_downgrade_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "NON_MONOTONIC_POLICY_VERSION"):
            self.authority.publish(tenant="tenant-a", policy_id="p", version=1)


if __name__ == "__main__":
    unittest.main()
