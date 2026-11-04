import os
from pathlib import Path
import tempfile
import unittest

from tools.activation_runtime.native_apx import evaluate


class NativeAPXMissingTests(unittest.TestCase):
    def test_missing_original_source_does_not_substitute(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileNotFoundError):
                evaluate(root, {"operation": "WBC", "witnessIds": [], "decisions": {"": "UNKNOWN"}})


@unittest.skipUnless(os.environ.get("QUALITYRAG_APX_ROOT"), "Pinned original APX checkout not configured")
class NativeAPXTests(unittest.TestCase):
    def test_canonical_wbc_reduction_and_negative_input(self):
        root = os.environ["QUALITYRAG_APX_ROOT"]
        result = evaluate(root, {"operation": "WBC", "witnessIds": ["a", "b"],
                                "decisions": {"": "UNKNOWN", "a": "SAT", "b": "UNKNOWN", "a,b": "SAT"}})
        self.assertEqual(result["result"]["w_min"], ["a"])
        self.assertTrue(result["result"]["verification"]["loadBearing"])
        self.assertFalse(result["can_generate"])
        with self.assertRaises(ValueError):
            evaluate(root, {"operation": "WBC", "witnessIds": ["a"], "decisions": {"a": "SAT"}})

    def test_canonical_rcoc_requires_known_applicability(self):
        root = os.environ["QUALITYRAG_APX_ROOT"]
        before = {"schema": "apx.semantic-assurance-snapshot/v0.1",
                  "coordinates": [{"id": "G"+str(n), "applicable": True, "deltaRef": 1} for n in range(1,13)]}
        import copy
        after = copy.deepcopy(before)
        after["coordinates"][0]["deltaRef"] = 0
        result = evaluate(root, {"operation": "RCOC", "before": before, "after": after})
        self.assertEqual(result["result"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["result"]["coordinates"][0]["movement"], "AWAY_FROM_ADMITTED_REGIME")
        after["coordinates"][0]["applicable"] = None
        with self.assertRaises(ValueError):
            evaluate(root, {"operation": "RCOC", "before": before, "after": after})
