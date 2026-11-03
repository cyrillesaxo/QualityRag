import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler import CompileError, inspect, project, main


class CompilerContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def assert_quarantined(self, report):
        self.assertGreater(len(report["candidate_constraints"]), 0)
        self.assertEqual(report["enforceability"]["automatically_enforceable"], 0)
        self.assertTrue(all(x["classification"] == "REVIEW_REQUIRED" for x in report["candidate_constraints"]))

    def test_yaml_preserves_semloan_must_constraints(self):
        p = self.file("semloan.yaml", """
pack_id: SEMLOAN
version: 0.4.0
loan_ledger:
  must_constraints:
    - id: SL-MUST-001
      rule: No loan may reach chapter end with an OUTSTANDING error.
    - id: SL-MUST-002
      rule: Every loan must declare its errors before refinement.
probes:
  - id: P_RETRIEVE
    mechanic: Cold retrieval required before claiming learner convergence.
""")
        report = inspect(p)
        self.assert_quarantined(report)
        self.assertEqual(report["source"]["pack_id"], "SEMLOAN")
        matches = [x for x in report["candidate_constraints"] if "SL-MUST" in x["location"] or "rule" in x["location"]]
        self.assertTrue(matches)

    def test_json_preserves_question_fan_invariants(self):
        p = self.file("question-fan.json", json.dumps({
            "pack": {"id": "apx.question-fan.discovery", "version": "0.1.0"},
            "algebra": {"invariants": [
                {"name": "choice_before_action", "expression": "!user_selected => !investigation_executed",
                 "description": "Investigation requires user selection"}
            ]}
        }))
        report = inspect(p)
        self.assert_quarantined(report)
        self.assertEqual(report["source"]["pack_id"], "apx.question-fan.discovery")
        self.assertTrue(any("investigation" in x["quotation"].lower() for x in report["candidate_constraints"]))

    def test_pdf_page_provenance_and_scanned_fail_closed(self):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        path = self.root / "rules.pdf"
        c = canvas.Canvas(str(path), pagesize=letter)
        c.drawString(30, 750, "The buyer comparison requires an independent baseline measurement.")
        c.showPage()
        c.drawString(30, 750, "Pilot claims must be tested before a sales statement.")
        c.save()
        report = inspect(path)
        self.assert_quarantined(report)
        self.assertTrue(any(x["location"].startswith("page:1:") for x in report["candidate_constraints"]))
        self.assertTrue(any(x["location"].startswith("page:2:") for x in report["candidate_constraints"]))
        blank = self.root / "blank.pdf"
        c = canvas.Canvas(str(blank), pagesize=letter)
        c.showPage()
        c.save()
        with self.assertRaisesRegex(CompileError, "OCR"):
            inspect(blank)

    def test_approval_and_integrity_guards(self):
        source = self.file("policy.json", json.dumps({"pack": {"id":"example","version":"1"},
            "specification": {"layer2_contract": {"required_planes": ["authority", "evidence"]},
                              "safety": "Must not conclude without verified custody"}}))
        report = inspect(source)
        candidate = report["candidate_constraints"][0]
        mapping = {
            "schema": "qualityrag.manual-mapping/v1",
            "source_sha256": report["source"]["sha256"],
            "policy_id": "projected-demo",
            "policy_version": "1.0",
            "rules": [{
                "candidate_id": candidate["candidate_id"],
                "requirement_id": "custody-evidence",
                "reviewed_by": "training-reviewer",
                "approved": True,
                "rationale": "Require a source witness for this declared obligation",
            }],
        }
        approved = project(report, mapping)
        self.assertEqual(approved["policy"]["requirements"][0]["id"], "custody-evidence")
        self.assertEqual(approved["mapping_receipts"][0]["semantic_enforcement"], "NOT_IMPLEMENTED")
        self.assertNotIn("refuse", json.dumps(approved).lower())
        tampered = {**mapping, "source_sha256": "0"*64}
        with self.assertRaisesRegex(CompileError,"fingerprint"):
            project(report, tampered)
        missing_approval = {**mapping, "rules":[{**mapping["rules"][0], "approved":False}]}
        with self.assertRaisesRegex(CompileError,"approval"):
            project(report, missing_approval)
        duplicate = {**mapping, "rules":mapping["rules"]*2}
        with self.assertRaisesRegex(CompileError,"Duplicate"):
            project(report, duplicate)
        incorrect_candidate = {**mapping, "rules":[{**mapping["rules"][0], "candidate_id": "NONEXISTENT"}]}
        with self.assertRaisesRegex(CompileError,"unknown"):
            project(report, incorrect_candidate)

    def test_cli_inspect_and_approved_project(self):
        source = self.file("governance.json", json.dumps({
            "pack":{"id":"governed","version":"1.2"},
            "algebra":{"invariants":[{"expression":"Every admitted claim requires an evidence witness"}]}
        }))
        report_path = self.root / "inspection.json"
        self.assertEqual(0, main([str(source), "--out", str(report_path)]))
        report = json.loads(report_path.read_text())
        mapping_path = self.root / "mapping.json"
        mapping_path.write_text(json.dumps({
            "schema":"qualityrag.manual-mapping/v1",
            "source_sha256":report["source"]["sha256"],
            "rules":[{"candidate_id":report["candidate_constraints"][0]["candidate_id"],
                      "requirement_id":"declared-witness","approved":True,
                      "reviewed_by":"training-reviewer",
                      "rationale":"Presence of a declared source witness is separately verifiable"}]}))
        output = self.root / "policy.json"
        self.assertEqual(0, main([str(source), "--out", str(report_path),
                                   "--mapping", str(mapping_path), "--policy-out", str(output)]))
        self.assertEqual(json.loads(output.read_text())["requirements"][0]["id"],"declared-witness")

    def test_rejects_unsupported_ambiguous_or_oversized_input(self):
        with self.assertRaises(CompileError):
            inspect(self.file("unknown.txt", "Constraint should be preserved"))
        with self.assertRaises(CompileError):
            inspect(self.file("bad.json", "[]"))
        with self.assertRaises(CompileError):
            inspect(self.file("large.json", "x"*2_000_001))

if __name__ == "__main__":
    unittest.main()
