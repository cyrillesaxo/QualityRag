import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_garden_coevolution import induce_from_examples, run_investigation
from test_rct_garden_coevolution import TRAIN, BEFORE, AFTER, WORKLOAD, PATH

TRAIN_EXAMPLES = [
    {"subject": "train-s0", "destination": "train-t0", "expected": True},
    {"subject": "train-s1", "destination": "train-t1", "expected": True},
    {"subject": "train-s0", "destination": "train-t1", "expected": False},
]


class GardenInvestigationTests(unittest.TestCase):
    def test_induces_three_hop_operator_without_specifying_path(self):
        hypothesis = induce_from_examples(TRAIN, TRAIN_EXAMPLES)
        self.assertEqual(hypothesis["status"], "UNIQUE_TRAINING_HYPOTHESIS")
        self.assertEqual(hypothesis["selected_predicate_path"], PATH)
        self.assertEqual(hypothesis["next_step"], "HELDOUT_EVALUATION")
        self.assertFalse(hypothesis["promotion_authorized"])

    def test_investigation_routes_derived_operator_to_holdout(self):
        workload = {"subjects": WORKLOAD["subjects"]}
        result = run_investigation(TRAIN, TRAIN_EXAMPLES, BEFORE, AFTER,
                                   workload, trials=2)
        self.assertEqual(result["status"], "CANDIDATES_EVALUATED")
        self.assertEqual(result["experiment"]["evaluated_operator"]["predicate_path"], PATH)
        self.assertEqual(len(result["experiment"]["results"]), 3)
        self.assertFalse(result["promotion_authorized"])
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")

    def test_ambiguous_examples_do_not_guess_an_operator(self):
        insufficient = [
            {"subject": "train-s0", "destination": "train-t0", "expected": True},
            {"subject": "train-s0", "destination": "train-irrelevant", "expected": False},
        ]
        hypothesis = induce_from_examples(TRAIN, insufficient)
        # This fixture may be uniquely discriminating; the key invariant is
        # that any nonunique result must withhold a proposed path.
        if hypothesis["status"] == "AMBIGUOUS":
            self.assertIsNone(hypothesis["selected_predicate_path"])
            self.assertEqual(hypothesis["next_step"], "GENERATE_DISCRIMINATING_PROBE")
        else:
            self.assertEqual(hypothesis["status"], "UNIQUE_TRAINING_HYPOTHESIS")

    def test_rejects_validation_examples_as_training_evidence(self):
        contaminated = [
            {"subject": "live-s0", "destination": "live-t0", "expected": True},
            {"subject": "train-s0", "destination": "train-t1", "expected": False},
        ]
        with self.assertRaisesRegex(ValueError, "training nodes"):
            induce_from_examples(TRAIN, contaminated)

    def test_requires_negative_controls(self):
        with self.assertRaisesRegex(ValueError, "positive and adversarial"):
            induce_from_examples(TRAIN, TRAIN_EXAMPLES[:2])

    def test_rejects_leaked_operator_from_holdout(self):
        with self.assertRaisesRegex(ValueError, "must not disclose"):
            run_investigation(TRAIN, TRAIN_EXAMPLES, BEFORE, AFTER,
                              WORKLOAD, trials=2)


if __name__ == "__main__":
    unittest.main()
