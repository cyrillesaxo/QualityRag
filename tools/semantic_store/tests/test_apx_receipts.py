"""APX receipt preservation tests: no bounded result becomes ADMIT."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from apx_receipts import record_apx_receipt, APXReceiptError, validate_receipt


class APXReceiptTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = SemanticStore(self.db)
        self.store.initialize()
        self.store.add_source("source", "v1", hashlib.sha256(b"source").hexdigest(), {})
        self.store.add_object("claim", "v1", "source", "v1", "CLAIM", {"value": "x"})

    def tearDown(self):
        self.db.close()

    def test_hcr_preserves_registered_family_bound(self):
        receipt = {
            "schema": "apx.hcr/v0.1", "engine": "HCR",
            "registry": {"digest": "registry-1"},
            "identifiability": {"status": "IDENTIFIED_WITHIN_REGISTRY"},
            "admission": {"status": "BOUNDED_DIAGNOSIS", "registry_digest": "registry-1"},
            "boundary": "Only inside the registered hypothesis family.",
        }
        result = record_apx_receipt(self.store, object_id="claim", revision="v1",
                                    engine="HCR", receipt=receipt)
        self.assertEqual(result["outcome"], "BOUNDED_DIAGNOSIS")
        self.assertEqual(result["admission"], "INCONCLUSIVE")
        self.assertEqual(result["authority"], "UNVERIFIED_EXTERNAL_RESULT")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM apx_receipts").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM apx_receipts")

    def test_hcr_does_not_accept_mismatched_registry(self):
        receipt = {
            "schema": "apx.hcr/v0.1", "engine": "HCR",
            "registry": {"digest": "registry-1"},
            "identifiability": {"status": "IDENTIFIED_WITHIN_REGISTRY"},
            "admission": {"status": "BOUNDED_DIAGNOSIS", "registry_digest": "registry-2"},
            "boundary": "Bounded.",
        }
        with self.assertRaises(APXReceiptError):
            validate_receipt("HCR", receipt)

    def test_rcoc_review_is_not_admitted(self):
        receipt = {
            "schema": "apx.rcoc-semantic-diff/v0.1",
            "status": "REVIEW_REQUIRED",
            "before": {"revision": "v1"},
            "after": {"revision": "v2"},
            "admission": {"status": "INCONCLUSIVE"},
            "boundary": "The diff is receipt-bounded.",
        }
        result = record_apx_receipt(self.store, object_id="claim", revision="v1",
                                    engine="RCOC", receipt=receipt)
        self.assertEqual(result["admission"], "INCONCLUSIVE")
        self.assertEqual(result["source_digests"]["after_revision"], "v2")

    def test_rcoc_rejects_false_bounded_diff_for_review_required(self):
        receipt = {
            "schema": "apx.rcoc-semantic-diff/v0.1",
            "status": "REVIEW_REQUIRED",
            "admission": {"status": "BOUNDED_DIFF"},
            "boundary": "Cannot auto-admit.",
        }
        with self.assertRaises(APXReceiptError):
            validate_receipt("RCOC", receipt)

    def test_missing_semantic_object_fails_atomically(self):
        receipt = {
            "schema": "apx.rcoc-semantic-diff/v0.1",
            "status": "INCOMPARABLE",
            "boundary": "Invalid snapshots.",
        }
        with self.assertRaises(sqlite3.IntegrityError):
            record_apx_receipt(self.store, object_id="missing", revision="v1",
                               engine="RCOC", receipt=receipt)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM apx_receipts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
