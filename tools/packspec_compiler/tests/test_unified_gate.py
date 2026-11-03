import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler import inspect
from typed_ir import compile_ir, _fingerprint
from unified_gate import evaluate_unified, guarded_generate, UnifiedGateError

SOURCE = {
    "pack_id":"unified-training",
    "version":"0.1",
    "rules":[
        {"rule":"A governing control must have source evidence"},
        {"rule":"Cold retrieval must occur after the original attempt"},
        {"rule":"A recorded probe must satisfy a bounded acceptance threshold"},
        {"rule":"Reviewer authority must be established before certification"}
    ]
}
NOW = "2026-11-02T10:05:00Z"

def approved(c, node_id, kind, parameters):
    return {"candidate_id":c["candidate_id"],"node_id":node_id,
            "kind":kind,"parameters":parameters,
            "approved":True,"reviewed_by":"training-reviewer",
            "rationale":"Specific reviewed projection bounded to source claim for testing"}

class UnifiedGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        source = Path(self.tmp.name) / "source.json"
        source.write_text(json.dumps(SOURCE))
        report = inspect(source)
        rules = [
          approved(report["candidate_constraints"][0],"required-control","EVIDENCE_PRESENCE",
                   {"requirement_id":"governing-control","min_independent_sources":1}),
          approved(report["candidate_constraints"][1],"order","TEMPORAL",
                   {"relation":"AFTER","anchor":"initial-attempt","subject":"cold-retrieval"}),
          approved(report["candidate_constraints"][2],"score","PROBE",
                   {"probe_id":"cold-recall","artifact_type":"TEST_RESULT","check":"NUMERIC_RANGE",
                    "field":"score","minimum":80,"maximum":100})
        ]
        self.ir=compile_ir(report,{"schema":"qualityrag.typed-mapping/v1",
              "source_sha256":report["source"]["sha256"],"rules":rules})
        self.witnesses=[{"id":"annex-1","requirement_id":"governing-control",
                         "origin":"compliance-annex","source_ref":"annex.pdf#187",
                         "status":"SUPPORTS","observed_at":"2026-11-02T09:00:00Z"}]
        self.observations={
           "events":{
             "initial-attempt":{"at":"2026-10-30T10:00:00Z","source_ref":"attempt/1"},
             "cold-retrieval":{"at":"2026-11-02T09:00:00Z","source_ref":"quiz/2"}
           },
           "probes":{
             "cold-recall":{"artifact_type":"TEST_RESULT","source_ref":"test/2",
                            "values":{"score":92}}
           }
        }
        self.calls=[]
        self.host_verifier=lambda source,witnesses,obs: (
            source["sha256"]==self.ir["source"]["sha256"] and
            len(witnesses)==1 and bool(obs["probes"]))

    def test_complete_and_attested_generates_once(self):
        outcome=guarded_generate(self.ir,self.witnesses,self.observations,NOW,
            lambda:self.calls.append("called") or "supported answer",
            verify_attestation=self.host_verifier)
        self.assertTrue(outcome["generated"])
        self.assertEqual(outcome["answer"],"supported answer")
        self.assertEqual(self.calls,["called"])
        decision=outcome["decision"]
        self.assertEqual(decision["verdict"],"ADMIT")
        self.assertEqual(decision["coverage"],
                         {"declared_nodes":3,"evidence_nodes":1,"semantic_nodes":2})
        self.assertEqual(decision["evidence"]["verdict"],"ADMIT")
        self.assertEqual(decision["semantics"]["verdict"],"ADMIT")

    def test_no_attestation_or_rejected_attestation_stops_generation(self):
        for verifier in (None,lambda a,b,c:False,lambda a,b,c:None,
                         lambda a,b,c: (_ for _ in ()).throw(RuntimeError("no key"))):
            with self.subTest(verifier=verifier):
                outcome=guarded_generate(self.ir,self.witnesses,self.observations,NOW,
                    lambda:self.fail("Generator must remain blocked"),
                    verify_attestation=verifier)
                self.assertFalse(outcome["generated"])
                self.assertEqual(outcome["decision"]["checks_verdict"],"ADMIT")
                self.assertEqual(outcome["decision"]["verdict"],"INCONCLUSIVE")

    def test_incomplete_evidence_blocks_even_when_semantics_pass(self):
        d=guarded_generate(self.ir,[],self.observations,NOW,
                           lambda:self.fail("No unsupported response"),verify_attestation=self.host_verifier)
        self.assertEqual(d["decision"]["verdict"],"INCONCLUSIVE")
        self.assertEqual(d["decision"]["evidence"]["verdict"],"INCONCLUSIVE")
        self.assertEqual(d["decision"]["semantics"]["verdict"],"ADMIT")

    def test_semantic_refusal_overrides_evidence_admission(self):
        obs=json.loads(json.dumps(self.observations))
        obs["probes"]["cold-recall"]["values"]["score"]=20
        d=guarded_generate(self.ir,self.witnesses,obs,NOW,
                           lambda:self.fail("Contradicted answer"),verify_attestation=self.host_verifier)
        self.assertEqual(d["decision"]["verdict"],"REFUSE")
        self.assertEqual(d["decision"]["evidence"]["verdict"],"ADMIT")
        self.assertEqual(d["decision"]["semantics"]["verdict"],"REFUSE")

    def test_evidence_refusal_overrides_inconclusive_semantics(self):
        witnesses=json.loads(json.dumps(self.witnesses))
        witnesses[0]["status"]="CONTRADICTS"
        obs=json.loads(json.dumps(self.observations))
        obs["events"].pop("cold-retrieval")
        d=evaluate_unified(self.ir,witnesses,obs,NOW,verify_attestation=self.host_verifier)
        self.assertEqual(d["verdict"],"REFUSE")
        self.assertEqual(d["semantics"]["verdict"],"INCONCLUSIVE")

    def test_deferred_authority_cannot_be_silently_omitted(self):
        ir=json.loads(json.dumps(self.ir))
        auth={
          "node_id":"authorization","kind":"AUTHORITY",
          "runtime":"NOT_IMPLEMENTED","status":"DEFERRED",
          "parameters":{"role":"certifier","scope":"learner award"},
          "review":ir["nodes"][0]["review"],
          "source":ir["nodes"][0]["source"]
        }
        ir["nodes"].append(auth)
        ir["summary"]["total"]+=1
        ir["summary"]["deferred_semantic_constraints"]+=1
        ir["ir_sha256"]=_fingerprint({"source_sha256":ir["source"]["sha256"],"nodes":ir["nodes"]})
        d=guarded_generate(ir,self.witnesses,self.observations,NOW,
                           lambda:self.fail("Authority not implemented"),verify_attestation=self.host_verifier)
        self.assertEqual(d["decision"]["verdict"],"INCONCLUSIVE")
        self.assertEqual(d["decision"]["semantics"]["findings"][-1]["reason"],
                         "RUNTIME_NOT_IMPLEMENTED")

    def test_only_evidence_or_only_semantic_nodes_still_enforce(self):
        for retained, expected in (("EVIDENCE_PRESENCE",{"evidence":"ADMIT","semantics":"NOT_APPLICABLE"}),
                                   ("TEMPORAL",{"evidence":"NOT_APPLICABLE","semantics":"ADMIT"})):
            ir=json.loads(json.dumps(self.ir))
            ir["nodes"]=[n for n in ir["nodes"] if n["kind"]==retained]
            ir["summary"]["total"]=1
            ir["summary"]["evidence_presence_projections"]=int(retained=="EVIDENCE_PRESENCE")
            ir["summary"]["deferred_semantic_constraints"]=int(retained!="EVIDENCE_PRESENCE")
            ir["ir_sha256"]=_fingerprint({"source_sha256":ir["source"]["sha256"],"nodes":ir["nodes"]})
            result=evaluate_unified(ir,self.witnesses,self.observations,NOW,
                                    verify_attestation=self.host_verifier)
            self.assertEqual(result["verdict"],"ADMIT")
            self.assertEqual(result["evidence"]["verdict"],expected["evidence"])
            self.assertEqual(result["semantics"]["verdict"],expected["semantics"])

    def test_tampering_and_incomplete_inventory_are_errors_not_admits(self):
        for mutation in ("fingerprint","lost-node","duplicated-node","unapproved"):
            ir=json.loads(json.dumps(self.ir))
            if mutation=="fingerprint":
                ir["nodes"][0]["parameters"]["requirement_id"]="different"
            if mutation=="lost-node":
                ir["nodes"].pop()
                ir["ir_sha256"]=_fingerprint({"source_sha256":ir["source"]["sha256"],"nodes":ir["nodes"]})
            if mutation=="duplicated-node":
                ir["nodes"].append(ir["nodes"][0])
                ir["summary"]["total"]+=1
                ir["summary"]["evidence_presence_projections"]+=1
                ir["ir_sha256"]=_fingerprint({"source_sha256":ir["source"]["sha256"],"nodes":ir["nodes"]})
            if mutation=="unapproved":
                ir["nodes"][0]["review"]["approved"]=False
                ir["ir_sha256"]=_fingerprint({"source_sha256":ir["source"]["sha256"],"nodes":ir["nodes"]})
            with self.subTest(mutation=mutation):
                with self.assertRaises(UnifiedGateError):
                    evaluate_unified(ir,self.witnesses,self.observations,NOW,
                                     verify_attestation=self.host_verifier)

    def test_attestation_callback_not_called_on_failed_checks(self):
        d=evaluate_unified(self.ir,[],self.observations,NOW,
                           verify_attestation=lambda a,b,c:self.fail("No verifier on failed checks"))
        self.assertEqual(d["verdict"],"INCONCLUSIVE")

if __name__=="__main__":
    unittest.main()
