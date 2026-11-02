import json
import unittest
from pathlib import Path
from qualityrag import evaluate
FIXTURES = json.loads((Path(__file__).resolve().parents[3] / "conformance/v0.1.json").read_text())
class ConformanceTest(unittest.TestCase):
    def test_all(self):
        for case in FIXTURES["cases"]:
            with self.subTest(case=case["name"]):
                evidence = [{"id":row[0],"origin":row[1],"status":row[2],
                    "requirement_id":"r","source_ref":"doc:"+row[0],
                    "observed_at":row[3] if len(row)>3 else "2026-11-02T10:00:00Z"} for row in case["evidence"]]
                result = evaluate(FIXTURES["pack"],evidence,as_of=FIXTURES["as_of"])
                self.assertEqual(result["verdict"],case["verdict"])
                self.assertEqual(result["findings"][0]["reasons"],case["reasons"])
