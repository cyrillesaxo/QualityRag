"""Load every training policy from external JSON rather than hardcoded fixtures."""
import json
from pathlib import Path
import tempfile
import unittest

from qualityrag import evaluate
from qualityrag.sources import from_properties

BASE = Path(__file__).resolve().parent
DATA = json.loads((BASE / "fixtures.json").read_text(encoding="utf-8"))

class ExternalPolicyTests(unittest.TestCase):
    def test_file_and_property_modes_share_verdicts(self):
        for domain in DATA["scenarios"]:
            file = BASE / "policies" / (domain["id"] + ".json")
            self.assertTrue(file.exists(), domain["id"])
            file_source = from_properties({
                "qualityrag.packspec.source": "file",
                "qualityrag.packspec.path": str(file),
            })
            property_source = from_properties({
                "qualityrag.packspec.source": "property",
                "qualityrag.packspec.json": file.read_text(encoding="utf-8"),
            })
            for case in domain["cases"]:
                with self.subTest(domain=domain["id"], case=case["id"]):
                    for loader in (file_source, property_source):
                        outcome = evaluate(loader(), case["evidence"], as_of=DATA["as_of"])
                        self.assertEqual(case["expected"], outcome["verdict"])

    def test_invalid_external_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "policy.json"
            file.write_text("{}", encoding="utf-8")
            loader = from_properties({
                "qualityrag.packspec.source": "file",
                "qualityrag.packspec.path": str(file),
            })
            with self.assertRaises(ValueError):
                loader()
            file.unlink()
            with self.assertRaises(FileNotFoundError):
                loader()

if __name__ == "__main__":
    unittest.main()
