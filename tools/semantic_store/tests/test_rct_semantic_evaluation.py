"""Drift evaluation accounting, adversarial controls, and no-pass-on-absence tests."""
import copy
from hashlib import sha256
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rct_semantic_evaluation import (
    evaluate_corpus, evaluate_native_corpus, lexical_change_baseline,
    load_corpus, validate_corpus)
from rct_native_semantic_host import NativeSemanticUnavailable


CORPUS=Path(__file__).resolve().parents[1]/"data"/"semantic_adversarial_v1.json"


class SemanticEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=load_corpus(CORPUS)

    def test_role_binding_stress_dataset_exposes_nonlexical_distinctions(self):
        stressed=load_corpus(
            Path(__file__).resolve().parents[1]/
            "data"/"semantic_role_binding_stress_v1.json")
        self.assertEqual(len(stressed["cases"]),18)
        self.assertEqual(sum(x["label"]=="DRIFT" for x in stressed["cases"]),12)
        self.assertEqual(sum(x["label"]=="NO_DRIFT" for x in stressed["cases"]),6)
        self.assertTrue(any("actor" in x["critical_distinction"].lower()
                            or "role" in x["critical_distinction"].lower()
                            for x in stressed["cases"]))
        r=evaluate_corpus(stressed,lexical_change_baseline,
                          detector_id="BYTE_INEQUALITY_STRESS")
        self.assertEqual(r["cases"],18)
        self.assertEqual(r["counts"]["consequential_detected"],12)
        self.assertEqual(r["counts"]["control_flagged"],6)
        self.assertFalse(r["can_generate"])

    def test_fixture_has_both_labels_and_multiple_domains(self):
        self.assertEqual(len(self.corpus["cases"]),30)
        self.assertEqual({x["domain"] for x in self.corpus["cases"]},{
            "nursing","hvac","driving","legal","finance","everyday"})
        self.assertEqual(sum(x["label"]=="DRIFT" for x in self.corpus["cases"]),18)
        self.assertEqual(sum(x["label"]=="NO_DRIFT" for x in self.corpus["cases"]),12)

    def test_naive_change_baseline_is_full_of_false_alarms(self):
        result=evaluate_corpus(self.corpus,lexical_change_baseline,
                               detector_id="TEXT_INEQUALITY_BASELINE")
        self.assertEqual(result["counts"]["consequential_detected"],18)
        self.assertEqual(result["counts"]["consequential_abstained"],0)
        self.assertEqual(result["counts"]["control_flagged"],12)
        self.assertEqual(result["counts"]["control_abstained"],0)
        self.assertEqual(result["consequential_detection_rate_lower_bound"],1.0)
        self.assertEqual(result["control_flag_rate"],1.0)
        self.assertLess(result["consequential_detection_wilson_95"][0], 0.85)
        self.assertEqual(result["consequential_detection_wilson_95"][1], 1.0)
        self.assertLess(result["control_flag_wilson_95"][0], 0.80)
        self.assertEqual(result["control_flag_wilson_95"][1], 1.0)
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_abstention_on_consequential_case_is_recorded_as_miss(self):
        def always_abstain(a,b):
            return {"source_sha256":sha256(a.encode()).hexdigest(),
                    "candidate_sha256":sha256(b.encode()).hexdigest(),
                    "verdict":"INCONCLUSIVE","can_generate":False,
                    "qualityrag_admission":"INCONCLUSIVE"}
        result=evaluate_corpus(self.corpus,always_abstain,detector_id="ALWAYS_ABSTAIN")
        self.assertEqual(result["counts"]["consequential_detected"],0)
        self.assertEqual(result["counts"]["consequential_abstained"],18)
        self.assertEqual(result["consequential_detection_rate_lower_bound"],0.0)
        self.assertEqual(len(result["cases_not_detected"]),18)
        self.assertEqual(result["control_flag_rate"],0.0)
        self.assertEqual(result["control_abstention_rate"],1.0)

    def test_forged_admit_and_mismatched_source_digests_rejected(self):
        def broken(a,b):
            return {"source_sha256":"0"*64,
                    "candidate_sha256":sha256(b.encode()).hexdigest(),
                    "verdict":"ADMIT","qualityrag_admission":"ADMIT",
                    "can_generate":True}
        with self.assertRaisesRegex(ValueError,"source-version"):
            evaluate_corpus(self.corpus,broken,detector_id="FORGED")

    def test_duplicate_missing_and_single_label_corpus_rejected(self):
        duplicate=copy.deepcopy(self.corpus)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            validate_corpus(duplicate)
        unlabeled=copy.deepcopy(self.corpus)
        unlabeled["cases"]=[x for x in unlabeled["cases"] if x["label"]=="DRIFT"]
        with self.assertRaisesRegex(ValueError,"Both consequential"):
            validate_corpus(unlabeled)
        mutated=copy.deepcopy(self.corpus)
        mutated["cases"][0]["label"]="SAFE"
        with self.assertRaises(ValueError):
            validate_corpus(mutated)

    def test_native_missing_engine_never_substitutes_naive_baseline(self):
        with self.assertRaises(NativeSemanticUnavailable):
            evaluate_native_corpus(self.corpus,
                                   apx_packages_root="/nonexistent/private/apx/packages")

    def test_repeatable_corpus_hash_and_outcomes(self):
        a=evaluate_corpus(self.corpus,lexical_change_baseline,detector_id="baseline")
        b=evaluate_corpus(load_corpus(CORPUS),lexical_change_baseline,detector_id="baseline")
        self.assertEqual(a["fingerprint"],b["fingerprint"])
        self.assertEqual(a["case_outcomes"],b["case_outcomes"])
        self.assertEqual(sum(a["counts"].values()),a["cases"])


if __name__=="__main__":
    unittest.main()
