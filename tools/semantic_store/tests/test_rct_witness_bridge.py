"""RCT v1.7 integration tests against canonical Python WitnessGraph evaluator."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_lens import compile_lens
from rct_witness_bridge import make_mapping, evaluate_witness_coverage

NOW = "2026-11-03T18:00:00Z"


def pack():
    return {"id":"lens-evidence","version":"1",
            "requirements":[
                {"id":"heart-evidence","min_independent_sources":2,
                 "scope":"anatomy","authority":"reviewed-source"},
                {"id":"occlusion-evidence","min_independent_sources":1,
                 "scope":"anatomy","authority":"reviewed-source"},
            ]}


def witness(wid, rid, origin, status="SUPPORTS", scope="anatomy"):
    return {"id":wid,"requirement_id":rid,"origin":origin,
            "source_ref":"unverified#"+wid,"status":status,
            "scope":scope,"authority":"reviewed-source",
            "observed_at":"2026-11-03T17:30:00Z"}


class TestRCTWitnessBridge(unittest.TestCase):
    def setUp(self):
        self.lens=compile_lens(
            "The heart is located in the thorax.",
            lens_id="anatomy",purpose="training",
            required=("heart-location",),
            permitted_omissions=("occlusion",))
        self.pack=pack()
        self.mapping=make_mapping(
            self.lens,pack=self.pack,
            predicate_requirements={
                "heart-location":"heart-evidence",
                "occlusion":"occlusion-evidence",
            })

    def assess(self,evidence,**kwargs):
        params={"lens":self.lens,"pack":self.pack,"mapping":self.mapping,
                "evidence":evidence,"as_of":NOW}
        params.update(kwargs)
        return evaluate_witness_coverage(**params)

    def test_distinct_labeled_origins_still_never_admit(self):
        evidence=[witness("a","heart-evidence","source-a"),
                  witness("b","heart-evidence","source-b"),
                  witness("c","occlusion-evidence","source-c")]
        result=self.assess(evidence)
        self.assertEqual(result["canonical_evidence_result"]["verdict"],"ADMIT")
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["distinction_coverage"]["heart-location"]
                         ["declared_independent_origin_count"],2)
        self.assertEqual(result["omission_authorization"],"NOT_ESTABLISHED")

    def test_same_origin_is_dependent_and_creates_wgap(self):
        result=self.assess([
            witness("a","heart-evidence","same"),
            witness("b","heart-evidence","same"),
            witness("c","occlusion-evidence","other")])
        self.assertEqual(result["canonical_evidence_result"]["verdict"],"INCONCLUSIVE")
        self.assertEqual(result["distinction_coverage"]["heart-location"]
                         ["missing_origin_count"],1)
        self.assertEqual(len(result["witness_graph"]["dependent_groups"]),1)
        self.assertEqual(result["witness_graph"]["dependent_groups"][0]["witness_ids"],
                         ["a","b"])
        self.assertEqual(len(result["wgap"]),1)

    def test_explicit_contradiction_refuses(self):
        result=self.assess([
            witness("a","heart-evidence","source-a"),
            witness("b","heart-evidence","source-b",status="CONTRADICTS"),
            witness("c","occlusion-evidence","source-c")])
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertIn("EVIDENCE_CONTRADICTION",result["blockers"])

    def test_missing_optional_omission_evidence_does_not_authorize(self):
        result=self.assess([
            witness("a","heart-evidence","source-a"),
            witness("b","heart-evidence","source-b")])
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertIn("EVIDENCE_GAPS_OR_UNRESOLVED_REQUIREMENTS",result["blockers"])
        self.assertEqual(result["distinction_coverage"]["occlusion"]
                         ["missing_origin_count"],1)

    def test_scope_mismatch_is_exposed(self):
        result=self.assess([
            witness("a","heart-evidence","source-a",scope="other"),
            witness("b","heart-evidence","source-b"),
            witness("c","occlusion-evidence","source-c")])
        self.assertIn("SCOPE_MISMATCH",
                      result["distinction_coverage"]["heart-location"]["reasons"])
        self.assertEqual(result["verdict"],"INCONCLUSIVE")

    def test_mapping_requires_all_required_and_optional_distinctions(self):
        with self.assertRaises(ValueError):
            make_mapping(self.lens,pack=self.pack,predicate_requirements={
                "heart-location":"heart-evidence"})

    def test_same_requirement_reused_for_two_distinctions_is_rejected(self):
        with self.assertRaises(ValueError):
            make_mapping(self.lens,pack=self.pack,predicate_requirements={
                "heart-location":"heart-evidence",
                "occlusion":"heart-evidence"})

    def test_tampered_mapping_rejected(self):
        modified={**self.mapping,"omission_authorization":"ESTABLISHED"}
        with self.assertRaises(ValueError):
            self.assess([],mapping=modified)

    def test_stale_source_is_rejected(self):
        changed={**self.lens,"source_sha256":"0"*64}
        with self.assertRaises(ValueError):
            self.assess([],lens=changed)

    def test_missing_pack_requirement_rejected(self):
        p=pack()
        p["requirements"].pop()
        with self.assertRaises(ValueError):
            self.assess([],pack=p)


if __name__=="__main__":
    unittest.main()
