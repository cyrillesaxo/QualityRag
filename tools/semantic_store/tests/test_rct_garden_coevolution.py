import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_garden_coevolution import (
    _reference_sql, _execute_path, _outgoing, run_research_cycle,
    synthesize_operators, SCHEMA)


def graph(prefix, revised=False):
    facts = []
    for i in range(5):
        chain = [
            (f"{prefix}s{i}", "belongs", f"{prefix}m{i}"),
            (f"{prefix}m{i}", "derives", f"{prefix}n{i}"),
            (f"{prefix}n{i}", "governs", f"{prefix}t{i}"),
        ]
        for j, (subject, predicate, target) in enumerate(chain):
            facts.append({"id": f"{prefix}{i}-{j}", "subject": subject,
                          "predicate": predicate, "object": target,
                          "source_ref": f"{prefix}src-{i}-{j}"})
    # Counterexample: unrelated edges must not count toward path composition.
    facts.append({"id": f"{prefix}noise", "subject": f"{prefix}s0",
                  "predicate": "unrelated", "object": f"{prefix}irrelevant",
                  "source_ref": f"{prefix}noise"})
    if revised:
        facts.append({"id": f"{prefix}new-governance",
                      "subject": f"{prefix}n0", "predicate": "governs",
                      "object": f"{prefix}new-target", "source_ref": f"{prefix}update"})
    return {"schema": "rct.structured-ast/v1", "facts": facts}


TRAIN = graph("train-")
BEFORE = graph("live-")
AFTER = graph("live-", revised=True)
PATH = ["belongs", "derives", "governs"]
WORKLOAD = {"predicate_path": PATH,
            "subjects": ["live-s0", "live-s0", "live-s0", "live-s1", "live-s4"]}


class GardenCoevolutionTests(unittest.TestCase):
    def test_synthesizes_three_hop_operator_from_training(self):
        candidates = synthesize_operators(TRAIN, max_path_length=3,
                                          max_proposals=24)
        matching = [c for c in candidates if c["predicate_path"] == PATH]
        self.assertEqual(len(matching), 1)
        self.assertGreaterEqual(matching[0]["support_path_count"], 5)
        self.assertEqual(matching[0]["qualityrag_admission"], "INCONCLUSIVE")
        self.assertFalse(matching[0]["promotion_authorized"])

    def test_sql_and_path_walker_agree_with_negative_controls(self):
        facts = BEFORE["facts"]
        subjects = ["live-s0", "live-s1", "live-irrelevant"]
        oracle = _reference_sql(facts, PATH, subjects)
        graph_index = _outgoing(facts)
        for subject in subjects:
            self.assertEqual(oracle[subject],
                             _execute_path(graph_index, PATH, subject))
        self.assertEqual(oracle["live-s0"], ("live-t0",))
        self.assertEqual(oracle["live-irrelevant"], ())

    def test_joint_evolution_preserves_revision_and_pareto(self):
        before = copy.deepcopy(BEFORE)
        result = run_research_cycle(
            TRAIN, BEFORE, AFTER, WORKLOAD, trials=2,
            max_proposals=24)
        self.assertEqual(BEFORE, before)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "CANDIDATES_EVALUATED")
        self.assertEqual(len(result["results"]), 6)
        self.assertTrue(result["pareto_candidate_indices"])
        self.assertEqual({x["grammar"] for x in result["results"]},
                         {"DIRECT_TRAVERSAL", "MATERIALIZED_COMPOSITION"})
        self.assertFalse(result["promotion_authorized"])
        self.assertIsNone(result["champion"])
        for policy in result["results"]:
            self.assertEqual(policy["operator_predicate_path"], PATH)
            self.assertEqual(policy["status"], "EXPERIMENTAL_CANDIDATE")
            for measure in policy["measurements"]:
                a, b = measure["before"], measure["after"]
                self.assertNotEqual(a["result_sha256"], b["result_sha256"])
                self.assertNotEqual(a["source_sha256"], b["source_sha256"])
                self.assertTrue(a["exact_reconstruction"])
                self.assertTrue(b["exact_reconstruction"])
                self.assertEqual(a["finite_structural_verdict"], "SAT")
                self.assertEqual(b["finite_structural_verdict"], "SAT")

    def test_hot_set_uses_workload_frequency(self):
        receipt = run_research_cycle(
            TRAIN, BEFORE, AFTER, WORKLOAD, trials=2,
            max_proposals=24)
        frequency = next(r for r in receipt["results"]
                         if r["activation"]["policy"] == "FREQUENCY_AWARE")
        self.assertEqual(frequency["activation"]["prefetch_subjects"],
                         ["live-s0", "live-s1"])

    def test_untrained_functional_relation_does_not_transfer(self):
        workload = {**WORKLOAD,
                    "predicate_path": ["belongs", "unknown", "governs"]}
        result = run_research_cycle(
            TRAIN, BEFORE, AFTER, workload, trials=2, max_proposals=24)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["promotion_authorized"])

    def test_unmodified_source_not_used_as_fake_update(self):
        with self.assertRaisesRegex(ValueError, "Revision must change"):
            run_research_cycle(TRAIN, BEFORE, BEFORE, WORKLOAD)

    def test_train_equals_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "Train/eval"):
            run_research_cycle(BEFORE, BEFORE, AFTER, WORKLOAD)

    def test_bad_workload_and_budget_refused(self):
        with self.assertRaisesRegex(ValueError, "Invalid research workload"):
            run_research_cycle(TRAIN, BEFORE, AFTER,
                               {**WORKLOAD, "subjects": []})
        with self.assertRaisesRegex(ValueError, "Invalid proposal"):
            run_research_cycle(TRAIN, BEFORE, AFTER, WORKLOAD, max_proposals=0)

    def test_unknown_derivation_not_silently_synthesized(self):
        candidates = synthesize_operators(TRAIN, max_path_length=4,
                                          max_proposals=24)
        self.assertTrue(all(c["type"] == "RELATION_PATH_COMPOSITION"
                            for c in candidates))
        self.assertTrue(all(2 <= len(c["predicate_path"]) <= 4
                            for c in candidates))


if __name__ == "__main__":
    unittest.main()
