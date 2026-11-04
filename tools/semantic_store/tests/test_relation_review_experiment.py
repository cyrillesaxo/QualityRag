"""Candidate relation review ledger tests: provenance, cost and fail-closed behavior."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from relation_review_experiment import run_candidate_review
from semantic_codex import CodexError


def fixture():
    manifest={
       "schema":"qualityrag.four-regime-input/v1.0",
       "sources":[
           {"id":"event","text":"Cyrille discussed a decision"},
           {"id":"decision","text":"A provisional decision was recorded"},
           {"id":"minutes","text":"Minutes mention the provisional decision"}],
       "relations":[{"from":"event","to":"decision","relation":"RELATES_TO"}],
       "witnesses":[{"target":"decision","source":"minutes"}],
       "questions":[{"id":"q1","term":"Cyrille","relation":"RELATES_TO",
                     "expected_targets":["decision"],"required_witnesses":["minutes"]}],
    }
    ledger={
       "schema":"qualityrag.relation-review-input/v1.1",
       "human_review_authentication":"UNVERIFIED",
       "candidate_relations":[{
           "from":"event","to":"decision","relation":"RELATES_TO",
           "role":"K","quoted_evidence":"Cyrille discussed a decision",
           "evidence_source":"event","review_verdict":"SUPPORTED",
           "extraction_ms":7.0,"review_ms":11.0}],
       "witness_reviews":[{"target":"decision","source":"minutes",
                           "review_verdict":"UNCERTAIN","review_ms":5.0}],
    }
    return manifest,ledger


class CandidateReviewTests(unittest.TestCase):
    def setUp(self):
        self.manifest,self.ledger=fixture()
        self.auth=lambda p,s,r:p=="reviewer" and s.startswith("regime/")

    def run_it(self):
        return run_candidate_review(self.manifest,self.ledger,principal="reviewer",
                                    authorize_source=self.auth,repetitions=1)

    def test_accounting_and_nonadmission(self):
        result=self.run_it()
        self.assertEqual(result["observed_costs_ms"]["total_caller_supplied"],23.0)
        self.assertEqual(result["typed_role_distribution"]["K"],1)
        self.assertEqual(result["candidate_counts"]["review_supported_unverified"],1)
        self.assertEqual(result["quote_anchor_failures"],[])
        self.assertEqual(result["automatic_relation_discovery"],"NOT_PERFORMED")
        self.assertEqual(result["false_positive_rate"],
                         "NOT_ESTABLISHED_INDEPENDENT_GROUND_TRUTH_REQUIRED")
        self.assertEqual(result["base_regime_experiment"]["question_results"][0]["r4_released_results"],0)
        self.assertEqual(result["admission"],"INCONCLUSIVE")
        self.assertFalse(result["can_generate"])

    def test_rejected_and_uncertain_labels_remain_visible(self):
        self.ledger["candidate_relations"][0]["review_verdict"]="REJECTED"
        out=self.run_it()
        self.assertEqual(out["candidate_counts"]["review_rejected"],1)
        self.assertEqual(out["packspec_evaluation"],"NOT_PERFORMED")

    def test_quote_absence_not_silently_verified(self):
        self.ledger["candidate_relations"][0]["quoted_evidence"]="unrelated text"
        out=self.run_it()
        self.assertEqual(out["quote_anchor_failures"][0]["status"],"SOURCE_QUOTE_NOT_FOUND")

    def test_duplicate_or_missing_relation_refused(self):
        self.ledger["candidate_relations"]=[]
        with self.assertRaises(CodexError):
            self.run_it()
        self.manifest,self.ledger=fixture()
        self.ledger["candidate_relations"].append(self.ledger["candidate_relations"][0])
        with self.assertRaises(CodexError):
            self.run_it()

    def test_witness_inventory_must_be_complete(self):
        self.ledger["witness_reviews"]=[]
        with self.assertRaises(CodexError):
            self.run_it()

    def test_nonfinite_costs_refused(self):
        for value in (-1,float("nan"),float("inf"),True):
            with self.subTest(value=value):
                self.ledger["candidate_relations"][0]["review_ms"]=value
                with self.assertRaises(CodexError):
                    self.run_it()

    def test_unauthorized_source_rejected(self):
        with self.assertRaises(PermissionError):
            run_candidate_review(self.manifest,self.ledger,
                principal="reviewer",
                authorize_source=lambda p,s,r:not s.endswith("minutes.json"),
                repetitions=1)

    def test_unrecognized_typed_role_refused(self):
        self.ledger["candidate_relations"][0]["role"]="PROVEN_TRUTH"
        with self.assertRaises(CodexError):
            self.run_it()

if __name__=="__main__":
    unittest.main()
