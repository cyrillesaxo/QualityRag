"""Lifecycle benchmarks must retain equal answers, update sensitivity and bounded scope."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_benchmark import make_fixture, make_contract
from rct_lifecycle import (
    make_cross_topology_fixture, run_lifecycle, run_cross_topology_suite
)

class TestRCTLifecycle(unittest.TestCase):
    def setUp(self):
        self.training = make_fixture(entities=24, prefix="train-")
        self.source = make_fixture(entities=40, prefix="eval-")
        self.contract = make_contract(self.source, repetitions=2)

    def test_complete_creation_update_and_query_costs(self):
        result = run_lifecycle(self.training, self.source, self.contract, trials=2)
        self.assertTrue(result["identical_answers"])
        self.assertTrue(result["mutation_changed_answers"])
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")
        self.assertFalse(result["packspec_verified"])
        self.assertNotEqual(result["source_sha256"], result["updated_source_sha256"])
        self.assertEqual(len(result["trials"]), 2)
        for backend in ("direct_sql", "materialized_sql", "candidate_lens"):
            data = result["median_ns"][backend]
            self.assertGreater(data["total_ns"], 0)
            self.assertGreaterEqual(data["total_ns"], data["query_ns"])
            self.assertGreater(data["shared_source_load_and_update_ns"], 0)
        self.assertIn(result["comparative_verdict"], (
            "CANDIDATE_LENS_LOWER_MEASURED_TOTAL",
            "SQL_BASELINE_EQUAL_OR_LOWER_MEASURED_TOTAL",
        ))
        self.assertEqual(result["strongest_sql_total_ns"], min(
            result["median_ns"]["direct_sql"]["total_ns"],
            result["median_ns"]["materialized_sql"]["total_ns"],
        ))

    def test_cross_topology_transfer_with_fanout_and_noise(self):
        result = run_cross_topology_suite(trials=1, repetitions=2)
        self.assertTrue(result["cross_topology_structural_equivalence"])
        self.assertEqual(set(result["topologies"]), {"chain", "branch"})
        self.assertNotEqual(
            result["topologies"]["chain"]["source_sha256"],
            result["topologies"]["branch"]["source_sha256"],
        )
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")
        branch = make_cross_topology_fixture(entity_count=24)
        self.assertTrue(any(f["predicate"] == "adjacent_to" for f in branch["facts"]))
        self.assertGreater(
            sum(f["predicate"] == "belongs_to" for f in branch["facts"]), 7
        )

    def test_wrong_source_contract_is_rejected(self):
        other = make_cross_topology_fixture(entity_count=24)
        with self.assertRaises(ValueError):
            run_lifecycle(self.training, other, self.contract, trials=1)

    def test_unbounded_requests_fail_closed(self):
        with self.assertRaises(ValueError):
            run_lifecycle(self.training, self.source, self.contract, trials=13)
        with self.assertRaises(ValueError):
            make_cross_topology_fixture(entity_count=201)

    def test_same_training_evaluation_rejected(self):
        contract = make_contract(self.training, repetitions=1)
        with self.assertRaises(ValueError):
            run_lifecycle(self.training, self.training, contract, trials=1)

if __name__ == "__main__":
    unittest.main()
