"""v0.9 workload economics: correctness and scope are mandatory; timing is advisory."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from rct_benchmark import (make_fixture,make_contract,run_benchmark,simulate_update)

class TestRCTWorkload(unittest.TestCase):
    def setUp(self):
        self.train = make_fixture(entities=24,prefix="training-")
        self.valid = make_fixture(entities=40,prefix="validation-")
        self.contract = make_contract(self.valid,repetitions=3)

    def test_all_backends_agree_on_same_workload(self):
        r=run_benchmark(self.valid,self.train,self.contract,trials=2)
        self.assertTrue(r["verified_identical_answers"])
        self.assertEqual(r["trial_count"],2)
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")
        self.assertEqual(r["result_status"],"EXPLORATORY_BENCHMARK")
        self.assertIn("direct_sql",r["medians"])
        self.assertIn("materialized_sql",r["medians"])
        self.assertIn("candidate_lens",r["medians"])
        self.assertEqual(r["queries_per_trial"],len({
            f["subject"] for f in self.valid["facts"]})*3)
        self.assertEqual(r["trials"][0]["output_sha256"],r["trials"][1]["output_sha256"])
        for values in r["medians"].values():
            self.assertGreaterEqual(values["total_ns"],values["build_ns"])
            self.assertGreater(values["query_ns"],0)

    def test_rebuild_after_update_matches_sql(self):
        r=simulate_update(self.valid,self.train,self.contract)
        self.assertEqual(r["status"],"STRUCTURALLY_MATCHED")
        self.assertTrue(r["recompiled"])
        self.assertNotEqual(r["old_sha256"],r["new_sha256"])
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")

    def test_source_fingerprint_mismatch_rejected(self):
        other=make_fixture(entities=44,prefix="other-")
        with self.assertRaises(ValueError):
            run_benchmark(other,self.train,self.contract,trials=1)

    def test_no_training_on_evaluation_source(self):
        with self.assertRaises(ValueError):
            run_benchmark(self.valid,self.valid,self.contract,trials=1)

    def test_unbounded_requests_rejected(self):
        with self.assertRaises(ValueError):
            run_benchmark(self.valid,self.train,self.contract,trials=16)
        invalid=dict(self.contract,repetitions=5000)
        with self.assertRaises(ValueError):
            run_benchmark(self.valid,self.train,invalid,trials=1)

    def test_wrong_purpose_rejected(self):
        invalid=dict(self.contract,purpose="clinical_decision")
        with self.assertRaises(ValueError):
            run_benchmark(self.valid,self.train,invalid,trials=1)

if __name__=="__main__":
    unittest.main()
