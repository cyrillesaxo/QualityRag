"""Read-only Garden projection tests (existing ledger, not duplicate state)."""
import sqlite3
import sys
import unittest
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P))
sys.path.insert(0, str(P.parent / "research_ledger"))
from ledger import initialize, claim, evidence, assess, link, verify_integrity
from rct_garden_projection import project_garden


class GardenProjectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize(self.db)
        claim(self.db, claim_id="garden.hypothesis.alpha", project="QualityRag",
              kind="HYPOTHESIS", statement="Prototype semantic grammar relation")
        claim(self.db, claim_id="garden.cycle.beta", project="QualityRag",
              kind="EXPERIMENT", statement="Bounded grammar activation comparison")
        evidence(self.db, evidence_id="test.fixture", kind="TEST_RESULT",
                 uri="https://example.org/fixture", description="Synthetic test reference")
        assess(self.db, event_id="open.alpha", claim_id="garden.hypothesis.alpha",
               assessment="INCONCLUSIVE", reason="No independently verified evidence",
               actor="test-actor", evidence_ids=["test.fixture"])
        assess(self.db, event_id="reopened.alpha", claim_id="garden.hypothesis.alpha",
               assessment="INCONCLUSIVE", reason="Dependency changed",
               actor="test-actor", evidence_ids=["test.fixture"])
        link(self.db, link_id="qualifies.beta.alpha", from_claim="garden.cycle.beta",
             to_claim="garden.hypothesis.alpha", relation="QUALIFIES")

    def tearDown(self):
        self.db.close()

    def test_projection_preserves_events_and_relations(self):
        p = project_garden(self.db)
        self.assertEqual(p["summary"]["branches"], 2)
        self.assertEqual(p["summary"]["garden_branches"], 2)
        self.assertEqual(p["summary"]["events"], 2)
        self.assertEqual(p["summary"]["relations"], 1)
        self.assertEqual(p["relations"][0]["relation"], "QUALIFIES")
        self.assertTrue(p["relations"][0]["target_visible"])
        self.assertEqual(p["branches"][0]["admission"], "NOT_ESTABLISHED")
        self.assertFalse(p["promotion_authorized"])
        self.assertEqual(p["ledger_integrity"], "CONSISTENT")
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_projections_are_read_only(self):
        before = self.db.total_changes
        a = project_garden(self.db)
        b = project_garden(self.db)
        self.assertEqual(a, b)
        self.assertEqual(self.db.total_changes, before)

    def test_boundaries_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "claim limit"):
            project_garden(self.db, maximum_claims=1)
        with self.assertRaisesRegex(ValueError, "event limit"):
            project_garden(self.db, maximum_events=1)
        with self.assertRaisesRegex(ValueError, "Invalid project"):
            project_garden(self.db, project="; DROP TABLE research_claims;")
        self.assertEqual(project_garden(self.db, project="Other")["summary"]["branches"], 0)

    def test_refutation_not_erased(self):
        assess(self.db, event_id="refuted.alpha", claim_id="garden.hypothesis.alpha",
               assessment="REFUTED", reason="Counterexample measured",
               actor="test-actor", evidence_ids=["test.fixture"])
        p = project_garden(self.db)
        branch = next(x for x in p["branches"]
                      if x["id"] == "garden.hypothesis.alpha")
        self.assertFalse(branch["active_research"])
        self.assertEqual(branch["assessment"], "REFUTED")
        self.assertEqual(len([e for e in p["events"]
                              if e["branch_id"] == branch["id"]]), 3)

    def test_event_chain_integrity_is_a_precondition(self):
        self.db.execute("DROP TRIGGER forbid_research_events_update")
        self.db.execute("UPDATE research_events SET reason='tampered'"
                        " WHERE event_id='open.alpha'")
        with self.assertRaisesRegex(ValueError, "integrity failure"):
            project_garden(self.db)


if __name__ == "__main__":
    unittest.main()
