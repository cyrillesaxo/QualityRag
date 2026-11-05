"""Garden dependency binding, replay invalidation and append-only tests."""
import copy
import sqlite3
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "research_ledger"))
from ledger import initialize, progress, verify_integrity
from rct_garden_lifecycle import register_cycle, inspect_revisions, reopen_on_revision, replay_after_revision
from rct_garden_coevolution import run_research_cycle
from test_rct_garden_coevolution import TRAIN, BEFORE, AFTER, WORKLOAD

ACTOR = "research-operator"
URI = "https://example.org/research/fixture"  # reference only; not authenticated


class GardenLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = run_research_cycle(
            TRAIN, BEFORE, AFTER, WORKLOAD, trials=2, max_proposals=24)
        cls.sources = {
            "training": cls.receipt["training_sha256"],
            "source": cls.receipt["source_sha256"],
            "revised": cls.receipt["revised_sha256"],
        }

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize(self.db)
        self.opened = register_cycle(self.db, self.receipt, sources=self.sources,
                                     evidence_uri=URI, actor=ACTOR)

    def tearDown(self):
        self.db.close()

    def test_source_bindings_are_inspectable(self):
        report = inspect_revisions(self.db, self.opened["claim_id"],
                                   observed_sources=self.sources)
        self.assertFalse(report["invalidated"])
        self.assertEqual(report["current_assessment"], "INCONCLUSIVE")
        self.assertFalse(report["can_generate"])
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_revision_appends_event_not_rewrite(self):
        mutated = dict(self.sources, source="a" * 64)
        report = reopen_on_revision(
            self.db, self.opened["claim_id"], observed_sources=mutated,
            evidence_uri=URI, actor=ACTOR)
        self.assertEqual(report["changed"], ["source"])
        self.assertTrue(report["event_appended"])
        self.assertTrue(report["replay_required"])
        items = progress(self.db)["claims"]
        self.assertEqual(len(items), 1)
        self.assertEqual(len(items[0]["events"]), 2)
        self.assertEqual(items[0]["status"], "INCONCLUSIVE")
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_repeat_observation_is_idempotent(self):
        changed = dict(self.sources, source="b" * 64)
        first = reopen_on_revision(self.db, self.opened["claim_id"],
                                    observed_sources=changed,
                                    evidence_uri=URI, actor=ACTOR)
        second = reopen_on_revision(self.db, self.opened["claim_id"],
                                     observed_sources=changed,
                                     evidence_uri=URI, actor=ACTOR)
        self.assertTrue(first["event_appended"])
        self.assertFalse(second["event_appended"])
        self.assertEqual(len(progress(self.db)["claims"][0]["events"]), 2)

    def test_unmodified_source_does_not_append(self):
        result = reopen_on_revision(self.db, self.opened["claim_id"],
                                     observed_sources=self.sources,
                                     evidence_uri=URI, actor=ACTOR)
        self.assertFalse(result["event_appended"])
        self.assertEqual(len(progress(self.db)["claims"][0]["events"]), 1)

    def test_missing_and_new_source_reported(self):
        observed = {"source": self.sources["source"], "new": "f" * 64}
        report = inspect_revisions(self.db, self.opened["claim_id"],
                                   observed_sources=observed)
        self.assertEqual(report["missing"], ["revised", "training"])
        self.assertEqual(report["unexpected"], ["new"])
        self.assertTrue(report["invalidated"])

    def test_receipt_forgery_rejected(self):
        forged = copy.deepcopy(self.receipt)
        forged["promotion_authorized"] = True
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            register_cycle(self.db, forged, sources=self.sources,
                           evidence_uri=URI, actor=ACTOR)
        self.assertEqual(progress(self.db)["counts"]["total"], 1)

    def test_source_manifest_must_match_receipt(self):
        forged_sources = dict(self.sources, training="0" * 64)
        with self.assertRaisesRegex(ValueError, "exact train"):
            register_cycle(self.db, self.receipt, sources=forged_sources,
                           evidence_uri=URI, actor=ACTOR)
        self.assertEqual(progress(self.db)["counts"]["total"], 1)

    def test_duplicate_registration_fail_closed(self):
        with self.assertRaises(sqlite3.IntegrityError):
            register_cycle(self.db, self.receipt, sources=self.sources,
                           evidence_uri=URI, actor=ACTOR)
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_real_replay_creates_new_versioned_experiment_and_link(self):
        from test_rct_garden_investigation import TRAIN_EXAMPLES
        later = copy.deepcopy(AFTER)
        later["facts"].append({
            "id": "live-replay-added", "subject": "live-n0",
            "predicate": "governs", "object": "live-next-revision",
            "source_ref": "new-revision"})
        outcome = replay_after_revision(
            self.db, self.opened["claim_id"], training=TRAIN,
            examples=TRAIN_EXAMPLES, source=BEFORE, revised_source=later,
            workload={"subjects": WORKLOAD["subjects"]},
            actor=ACTOR, observation_uri=URI, receipt_uri=URI, trials=2,
            max_proposals=24)
        self.assertEqual(outcome["status"], "REPLAYED_AS_UNVERIFIED_RESEARCH")
        self.assertTrue(outcome["replayed"])
        self.assertNotEqual(outcome["new_claim_id"], self.opened["claim_id"])
        self.assertFalse(outcome["promotion_authorized"])
        entries = progress(self.db)["claims"]
        self.assertEqual(len(entries), 2)
        followup = next(x for x in entries
                        if x["claim_id"] == outcome["new_claim_id"])
        self.assertEqual(followup["status"], "INCONCLUSIVE")
        self.assertEqual(followup["links"][0],
                         {"to": self.opened["claim_id"], "relation": "QUALIFIES"})
        initial = next(x for x in entries
                       if x["claim_id"] == self.opened["claim_id"])
        self.assertEqual(len(initial["events"]), 2)
        self.assertTrue(verify_integrity(self.db)["consistent"])

    def test_replay_is_noop_without_source_revision(self):
        from test_rct_garden_investigation import TRAIN_EXAMPLES
        result = replay_after_revision(
            self.db, self.opened["claim_id"], training=TRAIN,
            examples=TRAIN_EXAMPLES, source=BEFORE, revised_source=AFTER,
            workload={"subjects": WORKLOAD["subjects"]},
            actor=ACTOR, observation_uri=URI, receipt_uri=URI, trials=2)
        self.assertEqual(result["status"], "NO_CHANGED_DEPENDENCIES")
        self.assertFalse(result["replayed"])
        self.assertEqual(progress(self.db)["counts"]["total"], 1)

    def test_broken_ledger_integrity_rejected(self):
        # Direct edits are blocked by the existing immutable triggers.
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("UPDATE research_events SET reason='forged'")
        self.assertTrue(verify_integrity(self.db)["consistent"])


if __name__ == "__main__":
    unittest.main()
