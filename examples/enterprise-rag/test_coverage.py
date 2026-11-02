import unittest
from evaluate_coverage import load, assess, summarize, REQUIRED
class CoverageEvaluationTest(unittest.TestCase):
    def test_fail_closed_on_missing_obligations(self):
        rows=assess(load())
        self.assertEqual(len(rows),3)
        for row in rows:
            if not row["all_required_present"]:
                self.assertNotEqual(row["gate_verdict"],"ADMIT")
        self.assertGreaterEqual(summarize(rows)["qualityrag_abstentions_on_missing_requirements"],1)
    def test_metrics_bounded(self):
        rows=assess(load(),k=3)
        self.assertTrue(all(0<=row["coverage"]<=1 for row in rows))
        self.assertEqual(summarize(rows)["qualityrag_admissions_with_missing_requirements"],0)
if __name__=="__main__":unittest.main()
