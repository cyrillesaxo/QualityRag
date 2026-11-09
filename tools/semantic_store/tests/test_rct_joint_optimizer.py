import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_joint_optimizer import (ACTIVATIONS, GRAMMARS, SCHEMA,
                                 evaluate_joint_search)


def graph(prefix, *, add=False):
    facts = []
    for i in range(3):
        facts.extend([
            {"id": f"{prefix}a{i}", "subject": f"{prefix}s{i}",
             "predicate": "p", "object": f"{prefix}m{i}",
             "source_ref": f"{prefix}source-a{i}"},
            {"id": f"{prefix}b{i}", "subject": f"{prefix}m{i}",
             "predicate": "q", "object": f"{prefix}z{i}",
             "source_ref": f"{prefix}source-b{i}"},
        ])
    # A distractor is preserved in the exact reconstructed source, even if
    # it is not needed for p/q.
    facts.append({"id": f"{prefix}noise", "subject": f"{prefix}s0",
                  "predicate": "r", "object": f"{prefix}irrelevant",
                  "source_ref": f"{prefix}noise-source"})
    if add:
        facts.append({"id": f"{prefix}extra", "subject": f"{prefix}m0",
                      "predicate": "q", "object": f"{prefix}extra-z",
                      "source_ref": f"{prefix}update"})
    return {"schema": "rct.structured-ast/v1", "facts": facts}


TRAIN = graph("train-")
SOURCE = graph("live-")
UPDATED = graph("live-", add=True)
WORKLOAD = {"predicate_pair": ["p", "q"],
            "subjects": ["live-s0", "live-s2"], "repetitions": 2}


class JointOptimizerTests(unittest.TestCase):
    def test_all_six_policies_preserve_results_after_update(self):
        snapshot = copy.deepcopy(SOURCE)
        result = evaluate_joint_search(TRAIN, SOURCE, UPDATED, WORKLOAD, trials=2)
        self.assertEqual(SOURCE, snapshot)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(len(result["results"]), len(GRAMMARS) * len(ACTIVATIONS))
        self.assertTrue(result["pareto_candidates"])
        self.assertIsNone(result["champion"])
        self.assertFalse(result["promotion_authorized"])
        for policy in result["results"]:
            self.assertEqual(policy["finite_structural_verdict"], "SAT")
            self.assertEqual(policy["qualityrag_admission"], "INCONCLUSIVE")
            self.assertFalse(policy["can_generate"])
            for trial in policy["trials"]:
                before, after = trial["before"], trial["after"]
                self.assertNotEqual(before["answers_sha256"], after["answers_sha256"])
                self.assertNotEqual(before["source_sha256"], after["source_sha256"])
                self.assertTrue(before["exact_reconstruction"])
                self.assertTrue(after["exact_reconstruction"])
                self.assertTrue(before["finite_answer_equivalence"])
                self.assertTrue(after["finite_answer_equivalence"])
                self.assertNotEqual(before["activation_signals"]["source_sha256"],
                                    after["activation_signals"]["source_sha256"])

    def test_grammar_and_activation_are_independent_search_axes(self):
        result = evaluate_joint_search(TRAIN, SOURCE, UPDATED, WORKLOAD, trials=2)
        options = {(r["grammar"], r["activation"]) for r in result["results"]}
        self.assertEqual(options, {(g, a) for g in GRAMMARS for a in ACTIVATIONS})

    def test_disjoint_training_required(self):
        with self.assertRaisesRegex(ValueError, "Training and evaluation"):
            evaluate_joint_search(SOURCE, SOURCE, UPDATED, WORKLOAD, trials=2)

    def test_unseen_operator_not_invented(self):
        workload = dict(WORKLOAD)
        workload["predicate_pair"] = ["p", "unknown"]
        with self.assertRaisesRegex(ValueError, "No trained composition"):
            evaluate_joint_search(TRAIN, SOURCE, UPDATED, workload, trials=2)

    def test_update_must_change_source(self):
        with self.assertRaisesRegex(ValueError, "Update did not change"):
            evaluate_joint_search(TRAIN, SOURCE, SOURCE, WORKLOAD, trials=2)

    def test_invalid_workload_limits(self):
        bad = dict(WORKLOAD, repetitions=0)
        with self.assertRaisesRegex(ValueError, "Invalid workload"):
            evaluate_joint_search(TRAIN, SOURCE, UPDATED, bad, trials=2)
        with self.assertRaisesRegex(ValueError, "Invalid workload"):
            evaluate_joint_search(TRAIN, SOURCE, UPDATED, WORKLOAD, trials=1)

    def test_large_graph_rejected_before_materialization(self):
        huge = graph("train-")
        template = huge["facts"][0]
        for i in range(301):
            huge["facts"].append({**template, "id": f"extra{i}"})
        with self.assertRaisesRegex(ValueError, "Fact budget"):
            evaluate_joint_search(huge, SOURCE, UPDATED, WORKLOAD, trials=2)

    def test_negative_control_is_source_scoped(self):
        new_source = copy.deepcopy(UPDATED)
        new_source["facts"] = [f for f in new_source["facts"] if f["id"] != "live-extra"]
        with self.assertRaisesRegex(ValueError, "Update did not change"):
            evaluate_joint_search(TRAIN, SOURCE, new_source, WORKLOAD, trials=2)


if __name__ == "__main__":
    unittest.main()
