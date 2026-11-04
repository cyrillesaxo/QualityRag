"""Dependency uncertainty never inherits validation from historical status labels."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ledger

AT="2026-11-04T12:00:00Z"


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=sqlite3.connect(Path(self.temp.name)/"ledger.sqlite");self.addCleanup(self.db.close)
        ledger.initialize(self.db)
        for cid in ("parent","child","grandchild"):
            ledger.claim(self.db,claim_id=cid,project="other" if cid=="parent" else "fixture",kind="HYPOTHESIS",statement="Authored dependency fixture",at=AT)
        for eid,kind in (("review","REVIEW"),("test","TEST_RESULT")):
            ledger.evidence(self.db,evidence_id=eid,kind=kind,uri="https://example.invalid/fixture",description="Authored fixture",at=AT)

    def validate(self,cid):
        # Host callback is deliberately a test fixture, not scientific evidence.
        return ledger.assess(self.db,event_id="validated-"+cid,claim_id=cid,assessment="VALIDATED",
            reason="Fixture host callback",actor="fixture",evidence_ids=["review","test"],at=AT,
            verify_validation=lambda claim,evidence:True)

    def depend(self,child,parent):
        ledger.link(self.db,link_id=child+"-"+parent,from_claim=child,to_claim=parent,relation="DEPENDS_ON",at=AT)

    def item(self,cid,project=None):
        return next(item for item in ledger.progress(self.db,project)["claims"] if item["claim_id"]==cid)

    def test_unverified_cross_project_parent_blocks_validation_before_verifier(self):
        self.depend("child","parent")
        called=[]
        with self.assertRaisesRegex(ledger.LedgerError,"dependencies"):
            ledger.assess(self.db,event_id="v",claim_id="child",assessment="VALIDATED",reason="Must refuse",
                actor="fixture",evidence_ids=["review","test"],at=AT,verify_validation=lambda *args:called.append(True) or True)
        self.assertEqual(called,[])
        item=self.item("child","fixture")
        self.assertEqual(item["dependency_state"],"UNRESOLVED")
        self.assertEqual(item["dependency_blockers"],["parent"])

    def test_parent_refutation_propagates_without_rewriting_child_history(self):
        self.validate("parent");self.depend("child","parent");self.validate("child")
        self.depend("grandchild","child");self.validate("grandchild")
        self.assertEqual(self.item("grandchild")["effective_status"],"VALIDATED")
        ledger.assess(self.db,event_id="refuted-parent",claim_id="parent",assessment="REFUTED",
            reason="New adverse fixture",actor="fixture",evidence_ids=["test"],at="2026-11-04T12:00:01Z")
        for cid in ("child","grandchild"):
            item=self.item(cid,"fixture")
            self.assertEqual(item["status"],"VALIDATED")
            self.assertEqual(item["effective_status"],"INCONCLUSIVE")
            self.assertEqual(len(item["events"]),1)
        self.assertTrue(ledger.verify_integrity(self.db)["consistent"])
        counts=ledger.progress(self.db,"fixture")["counts"]
        self.assertEqual(counts["by_status"]["VALIDATED"],2)
        self.assertEqual(counts["by_effective_status"]["VALIDATED"],0)

    def test_cycle_cannot_bootstrap_historical_validations(self):
        self.validate("parent");self.validate("child")
        self.depend("child","parent");self.depend("parent","child")
        for cid in ("parent","child"):
            item=self.item(cid)
            self.assertEqual(item["effective_status"],"INCONCLUSIVE")
            self.assertEqual(item["dependency_state"],"UNRESOLVED")

    def test_dependency_context_binds_transitive_heads_and_graph_changes(self):
        self.depend("child","parent");self.depend("grandchild","child")
        before=ledger.dependency_context(ledger.progress(self.db)["claims"],"grandchild")
        self.assertEqual([item["claim_id"] for item in before],["child","parent"])
        self.validate("parent")
        after=ledger.dependency_context(ledger.progress(self.db)["claims"],"grandchild")
        self.assertNotEqual(before,after)
        self.assertIsNotNone(after[1]["head"])
