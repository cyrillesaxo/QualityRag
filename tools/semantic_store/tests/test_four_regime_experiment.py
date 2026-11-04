"""Four regime contrast: common questions, graph candidates and evidence refusals."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from four_regime_experiment import run_regime_contrast
from semantic_codex import CodexError


def fixture():
    return {
        "schema":"qualityrag.four-regime-input/v1.0",
        "sources":[
            {"id":"event","text":"Cyrille discussed the contract"},
            {"id":"decision","text":"The provisional decision was recorded"},
            {"id":"minutes","text":"Minutes include a reference to the provisional decision"},
        ],
        "relations":[{"from":"event","to":"decision","relation":"RELATES_TO"}],
        "witnesses":[{"target":"decision","source":"minutes"}],
        "questions":[
            {"id":"complete","term":"Cyrille","relation":"RELATES_TO",
             "expected_targets":["decision"],"required_witnesses":["minutes"]},
            {"id":"missing","term":"Cyrille","relation":"RELATES_TO",
             "expected_targets":["decision"],"required_witnesses":["event"]},
        ],
    }


class FourRegimeTests(unittest.TestCase):
    def setUp(self):
        self.manifest=fixture()
        self.policy=lambda principal,source,revision: (
            principal=="reviewer" and source.startswith("regime/"))

    def run_it(self,manifest=None,**kw):
        return run_regime_contrast(
            manifest if manifest is not None else self.manifest,
            repetitions=2,principal="reviewer",authorize_source=self.policy,**kw)

    def test_four_measured_regimes_and_policy_boundaries(self):
        result=self.run_it()
        self.assertEqual(len(result["regimes"]),4)
        self.assertEqual(len(result["question_results"]),4)
        for name,data in result["query_latency"].items():
            self.assertEqual(data["count"],4)
            self.assertGreaterEqual(data["median_ms"],0)
        one=result["question_results"][0]
        two=result["question_results"][1]
        self.assertEqual(one["r1_seed_count"],1)
        self.assertEqual(one["r2_seed_count"],1)
        self.assertEqual(one["r3_relation_candidate_count"],1)
        self.assertEqual(one["r3_finite_candidate_recall"],1)
        self.assertEqual(one["r4_gate"],"INCONCLUSIVE_SOURCE_AUTHENTICITY")
        self.assertEqual(two["r4_gate"],"REFUSE_MISSING_WITNESS_PRESENCE")
        self.assertTrue(all(x["r4_released_results"]==0
                            for x in result["question_results"]))
        self.assertEqual(result["trusted_packspec_evaluation"],"NOT_PERFORMED")
        self.assertEqual(result["semantic_equivalence"],
                         "NOT_ESTABLISHED_DIFFERENT_REGIME_CAPABILITIES")
        self.assertEqual(result["admission"],"INCONCLUSIVE")
        self.assertFalse(result["can_generate"])
        self.assertGreater(result["database_bytes"]["R4_WITNESS_REQUIREMENTS"],0)

    def test_repeat_experiment_fingerprint_stable(self):
        a,b=self.run_it(),self.run_it()
        self.assertEqual(a["manifest_fingerprint"],b["manifest_fingerprint"])
        self.assertEqual([x["r4_gate"] for x in a["question_results"]],
                         [x["r4_gate"] for x in b["question_results"]])

    def test_missing_relation_returns_no_candidate(self):
        self.manifest["questions"][0]["term"]="not present"
        r=self.run_it()
        self.assertEqual(r["question_results"][0]["r4_gate"],
                         "NO_RELATION_CANDIDATES")

    def test_access_restrictions_fail_closed(self):
        with self.assertRaises(PermissionError):
            run_regime_contrast(self.manifest,repetitions=1,
                                principal="reviewer",
                                authorize_source=lambda p,s,r:not s.endswith("minutes.json"))

    def test_unknown_source_or_duplicate_edge_fails(self):
        x=fixture()
        x["relations"][0]["to"]="unknown"
        with self.assertRaises(CodexError):
            self.run_it(x)
        x=fixture()
        x["witnesses"].append(x["witnesses"][0])
        with self.assertRaises(CodexError):
            self.run_it(x)

    def test_query_review_inventory_cannot_name_inaccessible_or_unknown(self):
        x=fixture()
        x["questions"][0]["required_witnesses"]=["ghost"]
        with self.assertRaises(CodexError):
            self.run_it(x)

    def test_no_verified_truth_from_unverified_review(self):
        r=self.run_it()
        self.assertEqual(r["labels_authenticity"],"CALLER_SUPPLIED_UNVERIFIED")
        self.assertEqual(r["full_lifecycle_cost"],"NOT_ESTABLISHED")
        self.assertTrue(all(x["admission"]=="INCONCLUSIVE"
                            for x in r["question_results"]))


if __name__=="__main__":
    unittest.main()
