import copy
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[0] / "research_ledger"))
from ledger import initialize, progress, verify_integrity
from rct_joint_optimizer import evaluate_joint_search
from rct_joint_ledger import append_joint_research
from test_rct_joint_optimizer import TRAIN, SOURCE, UPDATED, WORKLOAD


class JointLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize(self.db)
        self.receipt = evaluate_joint_search(
            TRAIN, SOURCE, UPDATED, WORKLOAD, trials=2)

    def tearDown(self):
        self.db.close()

    def test_reuses_ledger_with_inconclusive_state(self):
        result = append_joint_research(
            self.db, self.receipt,
            evidence_uri="https://example.org/experiment/receipt-a",
            actor="research-auditor")
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["ledger_integrity"], "CONSISTENT")
        entries = progress(self.db)["claims"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "INCONCLUSIVE")
        self.assertEqual(entries[0]["kind"], "EXPERIMENT")
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_cannot_promote_via_tampered_receipt(self):
        changed = copy.deepcopy(self.receipt)
        changed["qualityrag_admission"] = "ADMIT"
        with self.assertRaises(ValueError):
            append_joint_research(self.db, changed,
                                  evidence_uri="https://example.org/r",
                                  actor="research-auditor")
        self.assertEqual(progress(self.db)["counts"]["total"], 0)

    def test_duplicate_receipt_does_not_rewrite_history(self):
        args = {"evidence_uri": "https://example.org/r", "actor": "research-auditor"}
        append_joint_research(self.db, self.receipt, **args)
        with self.assertRaises(sqlite3.IntegrityError):
            append_joint_research(self.db, self.receipt, **args)
        self.assertTrue(verify_integrity(self.db)["consistent"])
        self.assertEqual(len(progress(self.db)["claims"]), 1)


if __name__ == "__main__":
    unittest.main()
