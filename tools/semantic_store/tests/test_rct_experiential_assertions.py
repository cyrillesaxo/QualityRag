"""Experiential claim binding regressions, using existing custody fixtures."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_experiential_assertions import assertion_binding, assess_experiential_assertions
from test_rct_source_custody import SourceCustodyTests

class ExperientialTests(unittest.TestCase):
    def setUp(self):
        self.custody = SourceCustodyTests("test_custodian_signs_matching_source_bytes")
        self.custody.setUp()
        self.addCleanup(self.custody.doCleanups)
        self.candidate = {"id": "illustrative", "origin": "HISTORICAL"}
        self.claims = [
            {"id":"claim-a","kind":"CAUSAL","text":"Claim A","requirement_id":"heart-evidence",
             "anchors":[{"witness_id":"a","root_id":"root-A","start_byte":0,"end_byte":7,"quote":"primary"}]},
            {"id":"claim-c","kind":"OUTCOME","text":"Claim C","requirement_id":"occlusion-evidence","anchors":[]}]
    def bind(self):
        c=self.custody
        return assertion_binding(self.candidate,self.claims,c.pack,c.records,c.source_bytes)
    def assess(self, *, sign_binding=True):
        c=self.custody
        if sign_binding:
            c.observations["experiential_binding"]=self.bind()
        signed, signed_custody=c._signed()
        from test_rct_signed_lineage import NOW
        return assess_experiential_assertions(candidate=self.candidate,claims=self.claims,
            lens=c.lens,reviewed_ir=c.ir,ir_binding=c.binding,evidence_pack=c.pack,
            witness_mapping=c.mapping,signed_policy=c.policy,signed_observations=signed,
            signed_custody=signed_custody,policy_keys={"policy":c.policy_key.public_key()},
            attestor_keys={"evidence":c.evidence_key.public_key()},
            custodian_keys={"custodian":c.custodian_key.public_key()},service="example",
            environment="test",minimum_sequence=1,nonce_accepted=c.nonces,
            witnesses=c.records,observations=c.observations,source_bytes=c.source_bytes,as_of=NOW)
    def test_signed_claims_remain_diagnostic(self):
        r=self.assess()
        self.assertFalse(r["can_generate"])
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")
        self.assertIn("CAUSAL_SUPPORT_UNVERIFIED",r["blockers"])
        self.assertIn("CLAIM_ANCHOR_MISSING",r["blockers"])
    def test_wrong_quote(self):
        self.claims[0]["anchors"][0]["quote"]="forged!"
        with self.assertRaisesRegex(ValueError,"exact primary bytes"): self.bind()
    def test_wrong_obligation(self):
        self.claims[0]["anchors"][0].update(witness_id="c",root_id="root-C")
        with self.assertRaisesRegex(ValueError,"obligation"): self.bind()
    def test_missing_claim(self):
        self.claims.pop()
        with self.assertRaisesRegex(ValueError,"Every PackSpec"): self.bind()
    def test_changed_candidate_invalidates_binding(self):
        self.custody.observations["experiential_binding"]=self.bind()
        self.candidate["origin"]="FICTIONAL"
        with self.assertRaisesRegex(ValueError,"bind exact experiential"): self.assess(sign_binding=False)
    def test_contradiction_preserved(self):
        self.custody.records[2]["status"]="CONTRADICTS"
        self.assertEqual(self.assess()["verdict"],"REFUSE")

if __name__=="__main__":
    unittest.main()
