"""Matched-query lifecycle economics must compare exactly the same answers."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from rct_matched_economics import run_matched_economics
from test_rct_purpose_lens import fixture, grammar


class MatchedEconomicsTest(unittest.TestCase):
    def setUp(self):
        self.training,self.training_labels=fixture("train-")
        self.source,self.labels=fixture("held-")
        self.spec=grammar()

    def run_economics(self,**updates):
        params=dict(training=self.training,
                    training_labels=self.training_labels,
                    source=self.source,labels=self.labels,grammar=self.spec,
                    purpose="classification-training",
                    required_predicates=["p","q","r"],
                    allowed_omission_predicates=["context"],
                    repetitions=2,trials=1)
        params.update(updates)
        return run_matched_economics(**params)

    def test_full_matched_workload_answer_equivalence(self):
        output=self.run_economics()
        self.assertTrue(output["matched_answer_equivalence"])
        self.assertEqual(output["queries_per_backend"],len({
            f["subject"] for f in self.source["facts"]})*2)
        self.assertEqual(output["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(output["can_generate"])
        self.assertEqual(set(output["median_total_ns"]),{
            "sql_direct","sql_materialized","rct_candidate"})
        for value in output["median_total_ns"].values():
            self.assertGreater(value,0)
        self.assertEqual(output["trials"][0]["verified_identical_query_answers"],True)
        self.assertGreater(output["trials"][0]["reference_compressed_bytes"],0)

    def test_bounded_inputs(self):
        for changed in (dict(trials=0),dict(repetitions=0),
                        dict(repetitions=101),dict(trials=11)):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    self.run_economics(**changed)

    def test_counterexample_disallows_economic_claim(self):
        source=dict(self.source,facts=[dict(f) for f in self.source["facts"]])
        source["facts"].append({
            "id":"adversarial-r","subject":"held-negative-path",
            "predicate":"r","object":"held-answer-n",
            "source_ref":"source#adversarial"})
        with self.assertRaisesRegex(ValueError,"Candidate cannot be compared"):
            self.run_economics(source=source)


if __name__=="__main__":
    unittest.main()
