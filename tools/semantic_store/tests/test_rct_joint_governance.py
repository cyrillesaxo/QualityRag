"""Joint canonical gate + WitnessGraph diagnostic integration tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))

from typed_ir import _fingerprint
from rct_lens import compile_lens
from rct_packspec_bridge import bind_candidate
from rct_witness_bridge import make_mapping
from rct_joint_governance import evaluate_joint_governance

NOW="2026-11-03T18:00:00Z"


def ir():
    source = "a"*64
    nodes=[{"node_id":"heart","kind":"EVIDENCE_PRESENCE",
            "runtime":"METADATA_GATE_V0_1","status":"PROJECTION_ONLY",
            "parameters":{"requirement_id":"heart-evidence",
                          "min_independent_sources":1},
            "source":{"source_sha256":source},
            "review":{"approved":True}}]
    return {"schema":"qualityrag.constraint-ir/v1",
            "source":{"sha256":source},
            "nodes":nodes,"summary":{"total":1,"evidence_presence_projections":1,
                                     "deferred_semantic_constraints":0},
            "ir_sha256":_fingerprint({"source_sha256":source,"nodes":nodes})}


def pack():
    return {"id":"joint-evidence","version":"1","requirements":[
        {"id":"heart-evidence","min_independent_sources":2},
        {"id":"occlusion-evidence","min_independent_sources":1}]}


def witness(id,rid,origin,status="SUPPORTS"):
    return {"id":id,"requirement_id":rid,"origin":origin,
            "status":status,"source_ref":"source#"+id,
            "observed_at":"2026-11-03T17:30:00Z"}


class JointGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.lens=compile_lens(
            "The heart is located in the thorax.",
            lens_id="heart",purpose="study",
            required=("heart-location",),permitted_omissions=("occlusion",))
        self.ir=ir()
        self.pack=pack()
        self.ir_binding=bind_candidate(self.lens,self.ir,purpose="study")
        self.witness_mapping=make_mapping(
            self.lens,pack=self.pack,predicate_requirements={
                "heart-location":"heart-evidence",
                "occlusion":"occlusion-evidence"})

    def run_gate(self,evidence):
        return evaluate_joint_governance(
            lens=self.lens,reviewed_ir=self.ir,ir_binding=self.ir_binding,
            evidence_pack=self.pack,witness_mapping=self.witness_mapping,
            witnesses=evidence,observations={},as_of=NOW)

    def test_metadata_checks_satisfied_but_combined_non_admitted(self):
        r=self.run_gate([
            witness("h1","heart-evidence","a"),
            witness("h2","heart-evidence","b"),
            witness("o1","occlusion-evidence","c")])
        self.assertEqual(r["unified_gate"]["canonical_checks_verdict"],"ADMIT")
        self.assertEqual(r["witness_coverage"]["canonical_evidence_result"]["verdict"],"ADMIT")
        self.assertEqual(r["verdict"],"INCONCLUSIVE")
        self.assertFalse(r["can_generate"])
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")
        self.assertIn("REVIEWED_IR_AND_EVIDENCE_PACK_SOURCE_BINDING_UNVERIFIED",
                      r["blockers"])

    def test_canonical_witness_gap_survives_unified_checks(self):
        r=self.run_gate([witness("h1","heart-evidence","a"),
                         witness("h2","heart-evidence","a"),
                         witness("o1","occlusion-evidence","b")])
        self.assertEqual(r["unified_gate"]["canonical_checks_verdict"],"ADMIT")
        self.assertEqual(r["witness_coverage"]["canonical_evidence_result"]["verdict"],
                         "INCONCLUSIVE")
        self.assertEqual(len(r["witness_coverage"]["witness_graph"]["dependent_groups"]),1)

    def test_contradictory_optional_requirement_refuses(self):
        r=self.run_gate([witness("h1","heart-evidence","a"),
                         witness("h2","heart-evidence","b"),
                         witness("o1","occlusion-evidence","c",status="CONTRADICTS")])
        self.assertEqual(r["witness_coverage"]["verdict"],"REFUSE")
        self.assertEqual(r["verdict"],"REFUSE")
        self.assertFalse(r["can_generate"])

    def test_mismatched_ir_binding_rejected(self):
        updated={**self.ir,"ir_sha256":"0"*64}
        with self.assertRaises(ValueError):
            evaluate_joint_governance(
                lens=self.lens,reviewed_ir=updated,ir_binding=self.ir_binding,
                evidence_pack=self.pack,witness_mapping=self.witness_mapping,
                witnesses=[],observations={},as_of=NOW)

if __name__=="__main__":
    unittest.main()
