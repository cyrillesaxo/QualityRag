"""Verify all APX-derived metadata-gate examples against the actual v0.1 SDK.

These are illustrative projections, not execution of original APX PackSpecs.
"""
import json
from pathlib import Path
import unittest
from qualityrag import evaluate

PATH = Path(__file__).with_name("fixtures.json")
DATA = json.loads(PATH.read_text(encoding="utf-8"))

class APXExamples(unittest.TestCase):
    def test_every_domain_and_verdict(self):
        self.assertEqual(len(DATA["scenarios"]), 5)
        for domain in DATA["scenarios"]:
            self.assertEqual({c["expected"] for c in domain["cases"]},
                             {"ADMIT", "REFUSE", "INCONCLUSIVE"})
            for case in domain["cases"]:
                with self.subTest(domain=domain["id"], case=case["id"]):
                    receipt = evaluate(domain["pack"], case["evidence"],
                                       as_of=DATA["as_of"])
                    self.assertEqual(case["expected"], receipt["verdict"])
                    if receipt["verdict"] != "ADMIT":
                        self.assertTrue(any(f["verdict"] != "ADMIT"
                                            for f in receipt["findings"]))

if __name__ == "__main__":
    unittest.main()
