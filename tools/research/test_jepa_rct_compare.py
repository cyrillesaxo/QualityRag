import json
import unittest
from pathlib import Path
from tools.research.jepa_rct_compare import evaluate

FIXTURE=Path(__file__).with_name("synthetic_manifest.json")

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(FIXTURE.read_text())

    def test_missing_runs_not_reported_as_results(self):
        result=evaluate(self.data)
        self.assertEqual(result["comparison_status"],"UNAVAILABLE")
        self.assertEqual(result["results"]["jepa"]["status"],"NOT_EVALUATED")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_role_swap_detected_and_not_admitted(self):
        responses={t["id"]:dict(t["gold"]) for t in self.data["tasks"]}
        responses["payment-role"]={"payer":"Bob","payee":"Alice"}
        for name in ("jepa","rct"):
            self.data["candidates"][name]={"status":"MEASURED","artifact_sha256":"test-placeholder-not-authenticated","model_or_grammar_version":"test","run_ref":"synthetic-test","responses":responses}
        result=evaluate(self.data)
        self.assertEqual(result["comparison_status"],"PAIRED_DECLARED_FIELDS_ONLY")
        self.assertIn("payment-role:payer",result["results"]["jepa"]["violations"])
        self.assertIn("payment-role:payee",result["results"]["rct"]["violations"])
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_missing_gold_fails(self):
        del self.data["tasks"][0]["gold"]
        with self.assertRaises(ValueError): evaluate(self.data)

    def test_partial_candidate_is_invalid(self):
        self.data["candidates"]["jepa"]={"status":"MEASURED","artifact_sha256":"x","model_or_grammar_version":"x","run_ref":"x","responses":{}}
        self.assertEqual(evaluate(self.data)["results"]["jepa"]["status"],"INVALID")

if __name__=="__main__":
    unittest.main()
