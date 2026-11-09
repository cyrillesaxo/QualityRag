import concurrent.futures
import os
import tempfile
import unittest

from qualityrag.protection import ProtectionDenied
from qualityrag.protection_sqlite import SQLitePolicyAuthority, SQLiteReplayStore


class SQLitePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "protection.db")

    def test_policy_persists_across_instances_and_restarts(self):
        first = SQLitePolicyAuthority(self.path)
        first.publish(tenant="a", policy_id="payments", version=1)
        second = SQLitePolicyAuthority(self.path)
        second.require_active(tenant="a", policy_id="payments", version=1)
        second.revoke(tenant="a", policy_id="payments")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            first.require_active(tenant="a", policy_id="payments", version=1)
        with self.assertRaisesRegex(ProtectionDenied, "NON_MONOTONIC_POLICY_VERSION"):
            first.publish(tenant="a", policy_id="payments", version=1)
        first.publish(tenant="a", policy_id="payments", version=2)
        SQLitePolicyAuthority(self.path).require_active(
            tenant="a", policy_id="payments", version=2)

    def test_policy_isolation(self):
        p = SQLitePolicyAuthority(self.path)
        p.publish(tenant="a", policy_id="payments", version=1)
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            p.require_active(tenant="b", policy_id="payments", version=1)

    def test_concurrent_policy_publish_has_single_winner(self):
        first = SQLitePolicyAuthority(self.path)
        second = SQLitePolicyAuthority(self.path)
        def publish(instance):
            try:
                instance.publish(tenant="a", policy_id="payments", version=1)
                return "ok"
            except ProtectionDenied as exc:
                return str(exc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, [first, second]))
        self.assertEqual(sorted(results), ["NON_MONOTONIC_POLICY_VERSION", "ok"])

    def test_atomic_policy_and_nonce_claim(self):
        p = SQLitePolicyAuthority(self.path)
        p.publish(tenant="a", policy_id="p", version=1)
        self.assertTrue(p.consume_if_active(
            tenant="a", policy_id="p", version=1,
            nonce="unique-claim", expires_at=1100, now=1000))
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            p.consume_if_active(
                tenant="b", policy_id="p", version=1,
                nonce="different-tenant", expires_at=1100, now=1000)
        self.assertFalse(SQLitePolicyAuthority(self.path).consume_if_active(
            tenant="a", policy_id="p", version=1,
            nonce="unique-claim", expires_at=1100, now=1000))

    def test_atomic_claim_denied_after_revocation(self):
        p = SQLitePolicyAuthority(self.path)
        p.publish(tenant="a", policy_id="p", version=1)
        p.revoke(tenant="a", policy_id="p")
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            p.consume_if_active(tenant="a", policy_id="p", version=1,
                                nonce="unspent", expires_at=1100, now=1000)
        p.publish(tenant="a", policy_id="p", version=2)
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            p.consume_if_active(tenant="a", policy_id="p", version=1,
                                nonce="unspent", expires_at=1100, now=1000)
        self.assertTrue(p.consume_if_active(
            tenant="a", policy_id="p", version=2,
            nonce="unspent", expires_at=1100, now=1000))

    def test_atomic_claim_races_with_revocation_without_unauthorized_approval(self):
        p = SQLitePolicyAuthority(self.path)
        p.publish(tenant="a", policy_id="p", version=1)
        # Both operations serialize at BEGIN IMMEDIATE. The claim either
        # occurs before revocation or gets denied; it never bypasses a
        # revocation committed before the claim.
        def claim():
            try:
                return p.consume_if_active(
                    tenant="a", policy_id="p", version=1,
                    nonce="race-nonce", expires_at=1100, now=1000)
            except ProtectionDenied as exc:
                return str(exc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            claimed = pool.submit(claim)
            revoked = pool.submit(p.revoke, tenant="a", policy_id="p")
            result = claimed.result()
            revoked.result()
        self.assertIn(result, [True, "POLICY_NOT_ACTIVE"])
        with self.assertRaisesRegex(ProtectionDenied, "POLICY_NOT_ACTIVE"):
            p.consume_if_active(tenant="a", policy_id="p", version=1,
                                nonce="next-nonce", expires_at=1100, now=1000)

    def test_replay_is_durable_and_atomic(self):
        first = SQLiteReplayStore(self.path)
        second = SQLiteReplayStore(self.path)
        self.assertTrue(first.consume("nonce1", expires_at=1100, now=1001))
        self.assertFalse(second.consume("nonce1", expires_at=1100, now=1002))
        self.assertFalse(SQLiteReplayStore(self.path).consume(
            "nonce1", expires_at=1100, now=1002))

    def test_concurrent_replay_has_single_winner(self):
        a = SQLiteReplayStore(self.path)
        b = SQLiteReplayStore(self.path)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(
                lambda store: store.consume("nonce1", expires_at=1100, now=1000),
                [a, b]))
        self.assertEqual(sorted(outcomes), [False, True])

    def test_expired_nonce_cannot_be_reused_while_valid(self):
        store = SQLiteReplayStore(self.path)
        self.assertTrue(store.consume("nonce1", expires_at=1010, now=1000))
        self.assertFalse(store.consume("nonce1", expires_at=1010, now=1010))
        self.assertFalse(store.consume("nonce1", expires_at=1010, now=1011))
        # After expiry, storage compaction permits reuse; release verifier
        # must separately reject an expired signed receipt before consume.
        self.assertTrue(store.consume("nonce2", expires_at=1030, now=1020))


if __name__ == "__main__":
    unittest.main()
