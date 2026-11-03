import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler import inspect
from typed_ir import compile_ir, _fingerprint
from semantic_runtime import evaluate_semantics, main

RULES = {"pack_id":"SEMLOAN","version":"0.4.0","rules":[
    {"rule":"Cold retrieval must occur after the learner's own attempt"},
    {"rule":"The retrieval probe must reach the documented correctness threshold"},
    {"rule":"Certification requires approved reviewer authority"}
]}
AT = "2026-11-02T10:05:00Z"

def approved(c, id, kind, params):
    return {"candidate_id":c["candidate_id"],"node_id":id,"kind":kind,
        "parameters":params,"approved":True,"reviewed_by":"training-domain-reviewer",
        "rationale":"Bounded operational assertion from a manually reviewed source clause"}

class SemanticRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path=Path(self.temp.name)/"rules.json"
        path.write_text(json.dumps(RULES),encoding="utf-8")
        report=inspect(path)
        c=report["candidate_constraints"]
        mapping={"schema":"qualityrag.typed-mapping/v1","source_sha256":report["source"]["sha256"],
            "rules":[
                approved(c[0],"order","TEMPORAL",{
                    "relation":"AFTER","anchor":"learner-attempt","subject":"cold-retrieval"}),
                approved(c[1],"score","PROBE",{
                    "probe_id":"recall-evaluation","artifact_type":"TEST_RESULT",
                    "check":"NUMERIC_RANGE","field":"score","minimum":80,"maximum":100})
            ]}
        self.ir=compile_ir(report,mapping)
        self.base={"events":{
          "learner-attempt":{"at":"2026-10-30T10:00:00Z","source_ref":"attempt#25"},
          "cold-retrieval":{"at":"2026-11-02T09:00:00Z","source_ref":"quiz#48"}
         },"probes":{"recall-evaluation":{"artifact_type":"TEST_RESULT",
             "source_ref":"graded-quiz#48","values":{"score":90}}}}

    def test_positive_checks_and_receipt(self):
        result=evaluate_semantics(self.ir,self.base,AT)
        self.assertEqual(result["verdict"],"ADMIT")
        self.assertEqual([r["verdict"] for r in result["findings"]],["ADMIT","ADMIT"])
        self.assertIn("UNAUTHENTICATED",result["assurance"])
        self.assertEqual(result,evaluate_semantics(self.ir,self.base,AT))

    def test_bad_order_and_wrong_probe_refuse(self):
        value=json.loads(json.dumps(self.base))
        value["events"]["cold-retrieval"]["at"]="2026-10-29T09:00:00Z"
        self.assertEqual(evaluate_semantics(self.ir,value,AT)["verdict"],"REFUSE")
        value=json.loads(json.dumps(self.base))
        value["probes"]["recall-evaluation"]["values"]["score"]=65
        self.assertEqual(evaluate_semantics(self.ir,value,AT)["verdict"],"REFUSE")

    def test_missing_and_malformed_data_inconclusive(self):
        for change in ("remove-probe","missing-source","naive-clock","wrong-artifact","type-confusion"):
            value=json.loads(json.dumps(self.base))
            if change=="remove-probe":value["probes"].clear()
            if change=="missing-source":value["events"]["cold-retrieval"].pop("source_ref")
            if change=="naive-clock":value["events"]["cold-retrieval"]["at"]="2026-11-02T09:00:00"
            if change=="wrong-artifact":value["probes"]["recall-evaluation"]["artifact_type"]="PRIMARY_RECORD"
            if change=="type-confusion":value["probes"]["recall-evaluation"]["values"]["score"]=True
            with self.subTest(change=change):
                self.assertEqual(evaluate_semantics(self.ir,value,AT)["verdict"],"INCONCLUSIVE")

    def test_deferred_semantics_cannot_admit(self):
        altered=json.loads(json.dumps(self.ir))
        altered["nodes"].append({
            "node_id":"authority","kind":"AUTHORITY","status":"DEFERRED",
            "runtime":"NOT_IMPLEMENTED",
            "parameters":{"role":"reviewer","scope":"learner certification"},
            "source":altered["nodes"][0]["source"],
            "review":altered["nodes"][0]["review"]
        })
        altered["ir_sha256"]=_fingerprint({
            "source_sha256":altered["source"]["sha256"],"nodes":altered["nodes"]})
        result=evaluate_semantics(altered,self.base,AT)
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertEqual(result["findings"][-1]["reason"],"RUNTIME_NOT_IMPLEMENTED")

    def test_tampering_rejected(self):
        value=json.loads(json.dumps(self.ir))
        value["nodes"][0]["parameters"]["relation"]="BEFORE"
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            evaluate_semantics(value,self.base,AT)
        value=json.loads(json.dumps(self.ir))
        value["nodes"][0]["review"]["approved"]=False
        value["ir_sha256"]=_fingerprint({
            "source_sha256":value["source"]["sha256"],"nodes":value["nodes"]})
        with self.assertRaisesRegex(ValueError,"Unreviewed"):
            evaluate_semantics(value,self.base,AT)

    def test_within_bounds_and_expiry(self):
        value=json.loads(json.dumps(self.ir))
        node=value["nodes"][0]
        node["parameters"]={"relation":"WITHIN","anchor":"learner-attempt",
                            "subject":"cold-retrieval","duration_seconds":3600}
        value["ir_sha256"]=_fingerprint({"source_sha256":value["source"]["sha256"],"nodes":value["nodes"]})
        self.assertEqual(evaluate_semantics(value,self.base,AT)["verdict"],"REFUSE")
        adjusted=json.loads(json.dumps(self.base))
        adjusted["events"]["cold-retrieval"]["at"]="2026-10-30T10:30:00Z"
        self.assertEqual(evaluate_semantics(value,adjusted,AT)["verdict"],"ADMIT")
        node["parameters"]={"relation":"EXPIRES_AT","anchor":"deadline"}
        value["ir_sha256"]=_fingerprint({"source_sha256":value["source"]["sha256"],"nodes":value["nodes"]})
        adjusted["events"]["deadline"]={"at":"2026-11-04T10:00:00Z","source_ref":"expiry-policy"}
        self.assertEqual(evaluate_semantics(value,adjusted,AT)["verdict"],"ADMIT")
        adjusted["events"]["deadline"]["at"]="2026-11-02T10:05:00Z"
        self.assertEqual(evaluate_semantics(value,adjusted,AT)["verdict"],"REFUSE")

    def test_cli_receipt(self):
        root=Path(self.temp.name)
        irfile=root/"ir.json"
        obsfile=root/"observations.json"
        output=root/"result.json"
        irfile.write_text(json.dumps(self.ir), encoding="utf-8")
        obsfile.write_text(json.dumps(self.base), encoding="utf-8")
        self.assertEqual(main(["--ir",str(irfile),"--observations",str(obsfile),
                               "--as-of",AT,"--out",str(output)]),0)
        result=json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["verdict"],"ADMIT")
        self.assertEqual(result["ir_sha256"],self.ir["ir_sha256"])

    def test_legacy_unbound_probes_remain_inconclusive(self):
        value=json.loads(json.dumps(self.ir))
        value["nodes"][1]["parameters"]={"probe_id":"recall-evaluation",
            "artifact_type":"TEST_RESULT","executor":"UNBOUND","result":"UNMEASURED"}
        value["nodes"][1]["runtime"]="NOT_IMPLEMENTED"
        value["nodes"][1]["status"]="DEFERRED"
        value["ir_sha256"]=_fingerprint({"source_sha256":value["source"]["sha256"],"nodes":value["nodes"]})
        self.assertEqual(evaluate_semantics(value,self.base,AT)["verdict"],"INCONCLUSIVE")

if __name__=="__main__":
    unittest.main()
