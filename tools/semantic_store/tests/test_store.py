"""Contract tests for the experimental, non-authoritative semantic store."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import SemanticStore


class SemanticStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.store = SemanticStore(self.connection)
        self.store.initialize()
        self.store.add_source("manual", "v1", hashlib.sha256(b"original").hexdigest(),
                              {"license": "test fixture"})
        self.store.add_object("claim", "v1", "manual", "v1", "CLAIM",
                              {"text": "Meter must be approved", "condition": "approved-meter"})
        self.store.add_object("witness", "v1", "manual", "v1", "WITNESS",
                              {"origin": "manual", "span": "section-1"})

    def tearDown(self):
        self.connection.close()

    def test_immutable_source_and_object_versions(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_source("manual", "v1", hashlib.sha256(b"changed").hexdigest(), {})
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_object("claim", "v1", "manual", "v1", "CLAIM", {"text": "changed"})
        self.assertEqual(self.store.object_version("claim", "v1")["condition"],
                         "approved-meter")

    def test_version_bound_witness_edges(self):
        self.store.add_edge("e1", "WITNESS", "claim", "v1", "witness", "v1",
                            "SUPPORTED_BY", {"source_group": "manual"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_edge("e2", "WITNESS", "claim", "v1",
                                "missing", "v1", "SUPPORTED_BY")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_edge("e3", "INVALID_LAYER", "claim", "v1",
                                "witness", "v1", "SUPPORTED_BY")

    def test_never_admits_unverified_or_missing_checks(self):
        for checks in ([], [{"id": "prerequisite", "status": "PASS"}],
                       [{"id": "prerequisite", "status": "UNKNOWN"}]):
            receipt = self.store.record_admission("claim", "v1", "policy-digest", checks)
            self.assertEqual(receipt.status, "INCONCLUSIVE")
            self.assertEqual(len(receipt.receipt_hash), 64)

    def test_explicit_failed_check_refuses(self):
        receipt = self.store.record_admission("claim", "v1", "policy-digest",
                                              [{"id": "prerequisite", "status": "FAIL"}])
        self.assertEqual(receipt.status, "REFUSE")

    def test_version_must_exist_before_receipt(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_admission("claim", "v2", "policy-digest", [])


if __name__ == "__main__":
    unittest.main()
