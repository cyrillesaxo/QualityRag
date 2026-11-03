"""Integration checks using the real experimental SemanticStore implementation."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_lens import compile_lens, persist_lens
from store import SemanticStore

SOURCE = "The human body has three main parts: head, trunk, and limbs. The heart is located in the thorax."

class TestRCTSourceLens(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = SemanticStore(self.db)
        self.store.initialize()

    def lens(self, lens_id="child", required=("head", "trunk", "limbs")):
        return compile_lens(SOURCE, lens_id=lens_id, purpose="anatomy",
                            required=required)

    def test_child_projection(self):
        lens = self.lens()
        self.assertEqual(lens["local_coverage"], "DECLARED_CLAIMS_PRESENT")
        self.assertEqual(len(lens["candidate_claims"]), 3)
        self.assertEqual(lens["qualityrag_admission"], "INCONCLUSIVE")
        for claim in lens["candidate_claims"]:
            self.assertEqual(SOURCE[claim["start"]:claim["end"]], claim["quote"])

    def test_missing_distinction_is_unknown(self):
        lens = compile_lens("The body has three main parts: head, trunk, and limbs.",
                            lens_id="clinical", purpose="heart", required=("heart-location",))
        self.assertEqual(lens["unresolved"], ["heart-location"])
        self.assertEqual(lens["local_coverage"], "UNKNOWN")

    def test_actual_store_persistence(self):
        lens = self.lens()
        result = persist_lens(self.store, lens=lens, source_id="source",
                              revision="v1", packspec_digest="packspec-v1")
        self.assertEqual(result["admission"], "INCONCLUSIVE")
        self.assertEqual(self.store.object_version(result["object_id"], "v1")["fingerprint"],
                         lens["fingerprint"])
        self.assertEqual(self.db.execute("SELECT verdict FROM admission_receipts").fetchone()[0],
                         "INCONCLUSIVE")

    def test_reject_tampering_without_writes(self):
        lens = self.lens()
        lens["qualityrag_admission"] = "ADMIT"
        with self.assertRaises(ValueError):
            persist_lens(self.store, lens=lens, source_id="source",
                         revision="v1", packspec_digest="p")
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_versions").fetchone()[0], 0)

    def test_multiple_lenses_share_source(self):
        for name, required in (("child", ("head",)), ("organ", ("heart-location",))):
            persist_lens(self.store, lens=self.lens(name, required), source_id="shared",
                         revision="v1", packspec_digest="p")
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_versions").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM semantic_versions").fetchone()[0], 2)

    def test_source_revision_mismatch_fails(self):
        persist_lens(self.store, lens=self.lens(), source_id="source",
                     revision="v1", packspec_digest="p")
        other = compile_lens("The body has three main parts: head, trunk, and limbs.",
                             lens_id="other", purpose="anatomy", required=("head",))
        with self.assertRaises(ValueError):
            persist_lens(self.store, lens=other, source_id="source",
                         revision="v1", packspec_digest="p")
        self.assertEqual(self.db.execute("SELECT count(*) FROM semantic_versions").fetchone()[0], 1)

    def test_omission_conflict(self):
        with self.assertRaises(ValueError):
            compile_lens(SOURCE, lens_id="child", purpose="regions",
                         required=("head",), permitted_omissions=("head",))

if __name__ == "__main__":
    unittest.main()
