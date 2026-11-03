"""Authenticated finite typed role graph: actual Ed25519 and durable replay."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"packspec_compiler"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy,sign_attestation,SignatureError
from signed_gate import SQLiteNonceStore
from test_rct_signed_lineage import constraint_ir,START,NOW,END
from test_rct_role_grammar import fact
from rct_signed_role_grammar import proposed_role_review,verify_signed_role_review


class SignedRoleGrammarTests(unittest.TestCase):
    def setUp(self):
        self.source="Alice must pay Bob."
        self.candidate="Bob must pay Alice."
        self.before=[fact(self.source,"payment","PAY",
                          OBLIGOR=("alice","Alice"),
                          BENEFICIARY=("bob","Bob"))]
        self.after=[fact(self.candidate,"payment","PAY",
                         OBLIGOR=("bob","Bob"),
                         BENEFICIARY=("alice","Alice"))]
        self.ir=constraint_ir()
        self.policy_key=Ed25519PrivateKey.generate()
        self.review_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",
            service="quality",environment="test",sequence=4,
            issued_at=START,expires_at=END)
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.nonce=SQLiteNonceStore(Path(tmp.name)/"role-nonce.db")
        self.counter=0

    def sign(self,proposal=None):
        if proposal is None:
            proposal=proposed_role_review(
                source=self.source,candidate=self.candidate,
                source_facts=self.before,candidate_facts=self.after,
                ir=self.ir)
            proposal["review_status"]="REVIEWED_FINITE_ROLE_BINDINGS"
        self.counter+=1
        return sign_attestation(
            [],{"typed_role_graph_review":proposal},
            self.review_key,key_id="role-reviewer",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce=f"role-review-{self.counter}",
            issued_at=START,expires_at=END)

    def verify(self,signed,**override):
        kw=dict(
            source=self.source,candidate=self.candidate,
            source_facts=self.before,candidate_facts=self.after,
            ir=self.ir,signed_policy=self.policy,signed_review=signed,
            policy_keys={"policy":self.policy_key.public_key()},
            reviewer_keys={"role-reviewer":self.review_key.public_key()},
            minimum_sequence=4,service="quality",environment="test",
            as_of=NOW,nonce_accepted=self.nonce)
        kw.update(override)
        return verify_signed_role_review(**kw)

    def test_signed_actor_swap_refuses_with_no_admission(self):
        r=self.verify(self.sign())
        self.assertEqual(r["verdict"],"REFUSE")
        self.assertTrue(r["signature_verified"])
        self.assertFalse(r["can_generate"])
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")
        self.assertEqual(r["semantic_completeness"],"UNKNOWN")

    def test_signed_same_semantic_roles_abstains(self):
        target="Bob must be paid by Alice."
        after=[fact(target,"payment","PAY",OBLIGOR=("alice","Alice"),
                    BENEFICIARY=("bob","Bob"))]
        original=self.candidate,self.after
        self.candidate=target
        self.after=after
        try:
            r=self.verify(self.sign())
            self.assertEqual(r["verdict"],"INCONCLUSIVE")
            self.assertFalse(r["can_generate"])
        finally:
            self.candidate,self.after=original

    def test_role_assignment_mutation_invalidates_signature(self):
        signed=self.sign()
        changed=[dict(self.after[0])]
        changed[0]["bindings"]=[
            dict(binding,entity="alice")
            if binding["role"]=="OBLIGOR" else binding
            for binding in self.after[0]["bindings"]]
        with self.assertRaisesRegex(ValueError,"Signed role graph review differs"):
            self.verify(signed,candidate_facts=changed)

    def test_review_replay_rejected(self):
        signed=self.sign()
        self.verify(signed)
        with self.assertRaises(SignatureError):
            self.verify(signed)

    def test_wrong_reviewer_key_rejected(self):
        signed=self.sign()
        with self.assertRaises(SignatureError):
            self.verify(signed,reviewer_keys={
                "role-reviewer":Ed25519PrivateKey.generate().public_key()})

    def test_unsigned_completeness_claim_rejected(self):
        draft=proposed_role_review(
            source=self.source,candidate=self.candidate,
            source_facts=self.before,candidate_facts=self.after,
            ir=self.ir)
        draft["completeness"]="PROVEN"
        draft["review_status"]="REVIEWED_FINITE_ROLE_BINDINGS"
        with self.assertRaisesRegex(ValueError,"Signed role graph review differs"):
            self.verify(self.sign(draft))

    def test_forged_policy_rejected(self):
        signed=self.sign()
        with self.assertRaises(SignatureError):
            self.verify(signed,policy_keys={
                "policy":Ed25519PrivateKey.generate().public_key()})


if __name__=="__main__":
    unittest.main()
