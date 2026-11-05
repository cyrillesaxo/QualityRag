"""Controller contract tests: external observation boundaries and bounded actions."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_garden_controller import run_controller, PROBE_SCHEMA
from test_rct_garden_coevolution import TRAIN, BEFORE, AFTER
from test_rct_garden_investigation import TRAIN_EXAMPLES


def ambiguous_training():
    source = copy.deepcopy(TRAIN)
    for i in (0, 1):
        edges = [
            (f"train-s{i}", "alternative_a", f"train-ax{i}"),
            (f"train-ax{i}", "alternative_b", f"train-ay{i}"),
            (f"train-ay{i}", "alternative_c", f"train-t{i}"),
        ]
        for j, (s, p, o) in enumerate(edges):
            source["facts"].append({
                "id": f"ambiguous-{i}-{j}", "subject": s, "predicate": p,
                "object": o, "source_ref": f"ambiguous-source-{i}-{j}"})
    return source


def external_answer(request):
    # This is a test-only controlled oracle with no model predictions.
    # It is NOT proof of independent authentication in production.
    expected = (request["subject"].startswith("train-s")
                and request["destination"] == request["subject"].replace(
                    "train-s", "train-t"))
    return {"schema": PROBE_SCHEMA, **request, "expected": expected,
            "evidence_ref": "test:independent-fixture-ground-truth",
            "oracle_id": "test-fixture-oracle",
            "authority": "EXTERNAL_UNVERIFIED"}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.workload = {"subjects": [
            "live-s0", "live-s0", "live-s1", "live-s2"]}

    def test_unique_hypothesis_executes_without_oracle(self):
        result = run_controller(
            TRAIN, TRAIN_EXAMPLES, BEFORE, AFTER, self.workload,
            oracle=None, max_probes=3, max_proposals=24)
        self.assertEqual(result["status"], "EVALUATED_UNVERIFIED")
        self.assertEqual(result["external_probe_count"], 0)
        self.assertEqual(len(result["investigation"]["experiment"]["results"]), 6)
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["can_generate"])

    def test_ambiguous_requires_external_oracle(self):
        result = run_controller(
            ambiguous_training(), TRAIN_EXAMPLES, BEFORE, AFTER,
            self.workload, oracle=None, max_probes=2, max_proposals=24)
        self.assertEqual(result["status"], "NEEDS_ORACLE")
        self.assertTrue(any(x["type"] == "PROBE_PROPOSED"
                            for x in result["events"]))
        self.assertEqual(result["external_probe_count"], 0)
        self.assertIsNone(result["investigation"])

    def test_oracle_receipt_can_discriminate_then_evaluate(self):
        calls = []
        def oracle(request):
            calls.append(copy.deepcopy(request))
            self.assertEqual(set(request), {"subject", "destination"})
            return external_answer(request)
        original = ambiguous_training()
        saved = copy.deepcopy(original)
        result = run_controller(
            original, TRAIN_EXAMPLES, BEFORE, AFTER, self.workload,
            oracle=oracle, max_probes=3, max_proposals=24)
        self.assertEqual(original, saved)
        self.assertEqual(result["status"], "EVALUATED_UNVERIFIED")
        self.assertGreaterEqual(result["external_probe_count"], 1)
        self.assertEqual(result["external_probe_count"], len(calls))
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")
        self.assertEqual(result["investigation"]["hypothesis"]["status"],
                         "UNIQUE_TRAINING_HYPOTHESIS")
        self.assertEqual(result["investigation"]["hypothesis"]["selected_predicate_path"],
                         ["belongs", "derives", "governs"])

    def test_budget_zero_cannot_infer_ambiguous_answer(self):
        result = run_controller(
            ambiguous_training(), TRAIN_EXAMPLES, BEFORE, AFTER,
            self.workload, oracle=external_answer, max_probes=0,
            max_proposals=24)
        self.assertEqual(result["status"], "BUDGET_EXHAUSTED")
        self.assertEqual(result["external_probe_count"], 0)

    def test_invalid_probe_receipt_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unsafe external probe"):
            run_controller(
                ambiguous_training(), TRAIN_EXAMPLES, BEFORE, AFTER,
                self.workload, oracle=lambda x: {**external_answer(x),
                                                "authority": "VERIFIED"},
                max_proposals=24)

    def test_probe_has_no_gold_metadata_or_holdout_source(self):
        def oracle(request):
            self.assertNotIn("source", request)
            self.assertNotIn("revised_source", request)
            self.assertNotIn("predicate_path", request)
            self.assertNotIn("expected", request)
            return external_answer(request)
        run_controller(ambiguous_training(), TRAIN_EXAMPLES, BEFORE,
                       AFTER, self.workload, oracle=oracle,
                       max_proposals=24)

    def test_no_training_negative_controls_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive and adversarial"):
            run_controller(
                TRAIN, TRAIN_EXAMPLES[:2], BEFORE, AFTER, self.workload)

    def test_invalid_probe_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid probe budget"):
            run_controller(
                TRAIN, TRAIN_EXAMPLES, BEFORE, AFTER, self.workload,
                max_probes=100)


if __name__ == "__main__":
    unittest.main()
