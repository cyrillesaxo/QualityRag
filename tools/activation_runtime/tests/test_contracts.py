import copy
import json
from pathlib import Path
import unittest
from tools.activation_runtime.contracts import CATALOG, NAMES, validate
from tools.activation_runtime.common import canonical, strict_json


class ContractTests(unittest.TestCase):
    def test_every_schema_is_valid(self):
        from jsonschema import Draft202012Validator
        for name in NAMES:
            Draft202012Validator.check_schema(json.loads((CATALOG / (name+".json")).read_text()))

    def test_invalid_operator_version_size_duplicates_and_type(self):
        from jsonschema import ValidationError
        from tools.activation_runtime.pipeline import encode
        raw = b'{"instruction":"NOT permitted","quantity":1}'
        artifact = encode(raw, {"instruction": "i", "quantity": "q"})
        validate("transform", artifact)
        self.assertEqual(strict_json(canonical(artifact)), artifact)
        for change in ({"schema": "qualityrag.finite-activation/v99"},
                       {"runtime": "unknown"}, {"payload": []}):
            with self.assertRaises(ValidationError):
                validate("transform", {**artifact, **change})
        with self.assertRaises(ValidationError):
            validate("operator-ast", {"op": "EXEC"})
        with self.assertRaises(ValueError):
            strict_json(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            validate("payload", {"a": "x"*524288})

    def test_actual_demo_receipts_match_schema(self):
        import tempfile
        from tools.activation_runtime.demo import run
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "run"
            result = run(output)
            validate("packspec", json.loads((output / "policy-ir.json").read_bytes()))
            for case in result["cases"]:
                validate("receipt", case["receipt"])
                validate("verdict", case["receipt"])
                validate("source", case["receipt"]["research_output"])
