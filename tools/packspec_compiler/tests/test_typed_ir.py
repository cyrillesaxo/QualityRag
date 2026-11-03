import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler import inspect, main, CompileError
from typed_ir import compile_ir, project_gate, draft_typed_mapping, IRValidationError

SOURCE = {
  "pack_id": "SEMLOAN", "version": "0.4.0",
  "loan_ledger": {"must_constraints": [
    {"rule": "Every loan must declare its errors before refinement"},
    {"rule": "Cold retrieval only after a prior learner attempt"}
  ]},
  "authority": {"rule": "Certification requires reviewer approval"},
  "probes": [{"rule": "A verified cold retrieval probe is required"}]
}

def approved(candidate, node_id, kind, params):
    return {"candidate_id": candidate["candidate_id"], "node_id": node_id,
            "kind": kind, "parameters": params, "approved": True,
            "reviewed_by": "independent-domain-owner",
            "rationale": "This is a deliberately scoped training interpretation requiring review"}

class TypedIRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "semloan.json"
        self.source.write_text(json.dumps(SOURCE), encoding="utf-8")
        self.report = inspect(self.source)
        self.candidates = self.report["candidate_constraints"]
        self.assertGreaterEqual(len(self.candidates), 4)
    def mapping(self, rules):
        return {"schema": "qualityrag.typed-mapping/v1",
                "source_sha256": self.report["source"]["sha256"],
                "rules": rules}

    def test_all_five_kinds_are_typed_but_four_are_deferred(self):
        raw = self.candidates
        rules = [
          approved(raw[0], "evidence", "EVIDENCE_PRESENCE",
                   {"requirement_id":"cold-retrieval", "min_independent_sources":2}),
          approved(raw[1], "timing", "TEMPORAL",
                   {"relation":"WITHIN", "anchor":"session-start", "duration_seconds":300}),
          approved(raw[2], "governance", "AUTHORITY",
                   {"role":"certifier", "scope":"current learner certification decision"}),
          approved(raw[3], "measurement", "PROBE",
                   {"probe_id":"cold-recall", "artifact_type":"TEST_RESULT"}),
          approved(raw[0], "meaning", "PREDICATE",
                   {"expression":"cold_retrieval_success && no_ai_shortcut"}),
        ]
        ir = compile_ir(self.report, self.mapping(rules))
        self.assertEqual(ir["summary"]["total"], 5)
        self.assertEqual(ir["summary"]["deferred_semantic_constraints"], 4)
        self.assertEqual(ir["summary"]["semantic_constraints_executed"], 0)
        self.assertEqual([x["status"] for x in ir["nodes"]],
                         ["PROJECTION_ONLY","DEFERRED","DEFERRED","DEFERRED","DEFERRED"])
        self.assertEqual(ir, compile_ir(self.report, self.mapping(rules)))
        projection = project_gate(ir, "demo-semloan")
        self.assertEqual(projection["policy"]["requirements"],
                         [{"id":"cold-retrieval","min_independent_sources":2}])
        self.assertEqual(len(projection["deferred_constraints"]), 4)
        self.assertEqual(projection["semantic_authorization"], "NOT_ESTABLISHED")

    def test_unapproved_and_source_drift_rejected(self):
        rule = approved(self.candidates[0],"evidence","EVIDENCE_PRESENCE",{"requirement_id":"cold-retrieval"})
        draft = draft_typed_mapping(self.report)
        self.assertFalse(any(x["approved"] for x in draft["rules"]))
        with self.assertRaises(IRValidationError):
            compile_ir(self.report, draft)
        with self.assertRaisesRegex(IRValidationError,"approval"):
            compile_ir(self.report,self.mapping([{**rule, "approved":False}]))
        bad = {**self.mapping([rule]), "source_sha256": "0"*64}
        with self.assertRaisesRegex(IRValidationError,"fingerprint"):
            compile_ir(self.report,bad)
        report = {**self.report, "limits":{**self.report["limits"],"truncated":True}}
        with self.assertRaisesRegex(IRValidationError,"Truncated"):
            compile_ir(report,self.mapping([rule]))

    def test_type_parameter_fail_closed(self):
        cases = [
          ("TEMPORAL",{"relation":"WITHIN","anchor":"begin","duration_seconds":-5}),
          ("AUTHORITY",{"role":"reviewer"}),
          ("PROBE",{"probe_id":"p","artifact_type":"unsupported"}),
          ("PREDICATE",{"expression":""}),
          ("EVIDENCE_PRESENCE",{"requirement_id":"correct","min_independent_sources":True}),
        ]
        for kind, params in cases:
            with self.subTest(kind=kind):
                rule=approved(self.candidates[0],"test",kind,params)
                with self.assertRaises(IRValidationError):
                    compile_ir(self.report,self.mapping([rule]))
        valid=approved(self.candidates[0],"evidence","EVIDENCE_PRESENCE",{"requirement_id":"ok"})
        with self.assertRaisesRegex(IRValidationError,"Duplicate node"):
            compile_ir(self.report,self.mapping([valid,valid]))
        one=approved(self.candidates[1],"other","EVIDENCE_PRESENCE",{"requirement_id":"ok"})
        with self.assertRaisesRegex(IRValidationError,"Duplicate evidence"):
            compile_ir(self.report,self.mapping([valid,one]))

    def test_deferred_only_never_projects_to_gate(self):
        rule = approved(self.candidates[0],"timing","TEMPORAL",
                        {"relation":"AFTER","anchor":"prior-attempt"})
        ir=compile_ir(self.report,self.mapping([rule]))
        with self.assertRaisesRegex(IRValidationError,"No enforceable"):
            project_gate(ir,"deferred-only")

    def test_cli_emits_review_and_typed_ir(self):
        draft=self.root/"draft.json";report_file=self.root/"report.json"
        self.assertEqual(main([str(self.source),"--out",str(report_file),
                               "--typed-draft-out",str(draft)]),0)
        self.assertFalse(json.loads(draft.read_text())["rules"][0]["approved"])
        mapping=self.root/"approved.json";irfile=self.root/"typed.json";policy=self.root/"policy.json"
        mapping.write_text(json.dumps(self.mapping([
          approved(self.candidates[0],"cold-retrieval","EVIDENCE_PRESENCE",
                   {"requirement_id":"cold-retrieval-evidence"})])),encoding="utf-8")
        self.assertEqual(main([str(self.source),"--out",str(report_file),
                               "--typed-mapping",str(mapping),"--ir-out",str(irfile),
                               "--typed-policy-out",str(policy),"--typed-policy-id","semloan-projection"]),0)
        self.assertEqual(json.loads(policy.read_text())["id"],"semloan-projection")
        self.assertEqual(json.loads(irfile.read_text())["summary"]["semantic_constraints_executed"],0)
