"""Research ledger contract tests: truth-status boundaries and append-only events."""
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ledger import initialize,claim,evidence,assess,link,progress,verify_integrity,LedgerError


class ResearchLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"progress.sqlite"
        self.db=sqlite3.connect(self.path)
        initialize(self.db)
        claim(self.db,claim_id="codex.visual.retrieval",project="QualityRag",
              kind="CAPABILITY",statement="Visual retrieval source indexing was implemented.")
        claim(self.db,claim_id="codex.visual.proven",project="QualityRag",
              kind="HYPOTHESIS",statement="Visual retrieval improves accuracy on a held-out corpus.")
        evidence(self.db,evidence_id="pull.58",kind="CODE_COMMIT",
                 uri="https://github.com/cyrillesaxo/QualityRag/pull/58",
                 description="Visual scene retrieval pull request, merge event")
        evidence(self.db,evidence_id="ci.58",kind="CI_RUN",
                 uri="https://github.com/cyrillesaxo/QualityRag/actions",
                 description="Repository CI tests; not an independent performance benchmark")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_implementation_does_not_imply_scientific_validation(self):
        assess(self.db,event_id="implementation.58",claim_id="codex.visual.retrieval",
               assessment="IMPLEMENTED",reason="Implementation merged",
               actor="repo-review",evidence_ids=["pull.58"])
        assess(self.db,event_id="tests.58",claim_id="codex.visual.retrieval",
               assessment="TESTED",reason="Automated CI passed",
               actor="repo-review",evidence_ids=["ci.58"])
        report=progress(self.db)
        states={x["claim_id"]:x["status"] for x in report["claims"]}
        self.assertEqual(states["codex.visual.retrieval"],"TESTED")
        self.assertEqual(states["codex.visual.proven"],"UNVERIFIED")
        with self.assertRaises(LedgerError):
            assess(self.db,event_id="invalid.validated",claim_id="codex.visual.proven",
                   assessment="VALIDATED",reason="No independent evaluator",
                   actor="repo-review",evidence_ids=["pull.58","ci.58"])

    def test_refutation_and_supersession_are_events_not_rewrites(self):
        assess(self.db,event_id="hypothesis.test",claim_id="codex.visual.proven",
               assessment="INCONCLUSIVE",reason="Only synthetic fixture evidence",
               actor="reviewer",evidence_ids=["ci.58"])
        assess(self.db,event_id="hypothesis.refuted",claim_id="codex.visual.proven",
               assessment="REFUTED",reason="Example reviewer classified result as refuted",
               actor="reviewer",evidence_ids=["ci.58"])
        link(self.db,link_id="depends.example",from_claim="codex.visual.proven",
             to_claim="codex.visual.retrieval",relation="DEPENDS_ON")
        item=next(x for x in progress(self.db)["claims"] if x["claim_id"]=="codex.visual.proven")
        self.assertEqual(item["status"],"REFUTED")
        self.assertEqual([x["assessment"] for x in item["events"]],
                         ["INCONCLUSIVE","REFUTED"])
        self.assertEqual(item["links"][0]["relation"],"DEPENDS_ON")
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_immutable_and_idempotency_boundary(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("UPDATE research_claims SET statement='different'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("DELETE FROM research_evidence")
        with self.assertRaises(sqlite3.IntegrityError):
            claim(self.db,claim_id="codex.visual.retrieval",project="QualityRag",
                  kind="CAPABILITY",statement="Attempt to silently overwrite")

    def test_evidence_type_controls_claim_status(self):
        with self.assertRaises(LedgerError):
            assess(self.db,event_id="bad",claim_id="codex.visual.retrieval",
                   assessment="IMPLEMENTED",reason="Mistaking tests for deployment",
                   actor="reviewer",evidence_ids=["ci.58"])
        with self.assertRaises(LedgerError):
            assess(self.db,event_id="bad2",claim_id="codex.visual.retrieval",
                   assessment="TESTED",reason="Mistaking a commit for tests",
                   actor="reviewer",evidence_ids=["pull.58"])
        with self.assertRaises(LedgerError):
            assess(self.db,event_id="bad3",claim_id="codex.visual.retrieval",
                   assessment="REFUTED",reason="Unsupported refutation",
                   actor="reviewer",evidence_ids=[])

    def test_cross_session_persistent_reopen(self):
        assess(self.db,event_id="implemented",claim_id="codex.visual.retrieval",
               assessment="IMPLEMENTED",reason="Merged code",
               actor="reviewer",evidence_ids=["pull.58"])
        self.db.close()
        self.db=sqlite3.connect(self.path)
        initialize(self.db)
        self.assertEqual(progress(self.db)["counts"]["by_status"]["IMPLEMENTED"],1)
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_hash_chain_detects_accidental_modification(self):
        assess(self.db,event_id="implemented",claim_id="codex.visual.retrieval",
               assessment="IMPLEMENTED",reason="Merged code",
               actor="reviewer",evidence_ids=["pull.58"])
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("UPDATE research_events SET reason='tamper'")
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_rejects_nonexistent_evidence(self):
        with self.assertRaises(LedgerError):
            assess(self.db,event_id="missing",claim_id="codex.visual.retrieval",
                   assessment="TESTED",reason="Missing receipt",
                   actor="reviewer",evidence_ids=["not.on.disk"])

if __name__=="__main__":
    unittest.main()
