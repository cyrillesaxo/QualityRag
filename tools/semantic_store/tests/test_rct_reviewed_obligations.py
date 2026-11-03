"""Signed review mapping uses canonical policy and observation verification."""
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy, sign_attestation, SignatureError
from signed_gate import SQLiteNonceStore
from rct_end_to_end import run_structural_pipeline
from rct_reviewed_obligations import proposed_review_record, verify_reviewed_mapping
from test_rct_purpose_lens import fixture, grammar
from test_rct_signed_lineage import constraint_ir, START, NOW, END


class ReviewedMappingTests(unittest.TestCase):
    def setUp(self):
        t, tlabels=fixture("train-")
        s, labels=fixture("held-")
        self.structural=run_structural_pipeline(
            t,tlabels,s,labels,grammar(),purpose="classification-training",
            lens_id="review-example",required_predicates=["p","q","r"],
            allowed_omission_predicates=["context"])
        self.lens=self.structural["purpose_lens"]
        self.conservation=self.structural["conservation"]
        self.ir=constraint_ir()
        self.policy_key=Ed25519PrivateKey.generate()
        self.review_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",service="quality",
            environment="test",sequence=4,issued_at=START,expires_at=END)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nonces=SQLiteNonceStore(Path(self.tmp.name)/"review-nonce.db")
        self.counter=0

    def signed(self, record=None, *, policy=None):
        self.counter+=1
        if record is None:
            record=proposed_review_record(
                self.lens,self.ir,self.conservation)
            record["review_verdict"]="REVIEWED_FINITE_SCOPE"
        policy=self.policy if policy is None else policy
        return sign_attestation(
            [],{"rct_semantic_review":record},self.review_key,key_id="reviewer",
            policy_signature=policy["signature"],service="quality",
            environment="test",nonce="review-"+str(self.counter),
            issued_at=START,expires_at=END)

    def verify(self, signed_review, **overrides):
        kwargs={
            "lens":self.lens,"ir":self.ir,
            "conservation":self.conservation,"signed_policy":self.policy,
            "signed_review":signed_review,
            "reviewer_keys":{"reviewer":self.review_key.public_key()},
            "policy_keys":{"policy":self.policy_key.public_key()},
            "minimum_sequence":4,"service":"quality","environment":"test",
            "as_of":NOW,"nonce_accepted":self.nonces}
        kwargs.update(overrides)
        return verify_reviewed_mapping(**kwargs)

    def test_finite_review_passes_signature_never_semantic_admission(self):
        signed=self.signed()
        result=self.verify(signed)
        self.assertEqual(result["review_record_signature"],"VERIFIED")
        self.assertEqual(result["reviewed_required_count"],3)
        self.assertEqual(result["reviewed_omission_count"],4)
        self.assertEqual(result["semantic_completeness"],"UNKNOWN")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(result["can_generate"])

    def test_missing_reviewer_signature_fails(self):
        signed=self.signed()
        signed["signature"]="A"*86
        with self.assertRaises(SignatureError):
            self.verify(signed)

    def test_changed_omission_or_partial_ir_node_inventory_fails(self):
        record=proposed_review_record(self.lens,self.ir,self.conservation)
        record["review_verdict"]="REVIEWED_FINITE_SCOPE"
        record["omitted_fact_ids"]=[]
        with self.assertRaisesRegex(ValueError,"reviewed obligation"):
            self.verify(self.signed(record))
        record=proposed_review_record(self.lens,self.ir,self.conservation)
        record["review_verdict"]="REVIEWED_FINITE_SCOPE"
        record["reviewed_ir_node_ids"]=[]
        with self.assertRaisesRegex(ValueError,"reviewed obligation"):
            self.verify(self.signed(record))

    def test_replay_rejected(self):
        signed=self.signed()
        self.verify(signed)
        with self.assertRaises(SignatureError):
            self.verify(signed)

    def test_forged_governing_policy_fails(self):
        signed=self.signed()
        with self.assertRaises(SignatureError):
            self.verify(signed,policy_keys={"policy":Ed25519PrivateKey.generate().public_key()})

    def test_unsigned_source_mutation_fails_before_review(self):
        lens=dict(self.lens)
        lens["purpose"]="different"
        signed=self.signed()
        with self.assertRaises(ValueError):
            self.verify(signed,lens=lens)

    def test_unknown_reviewer_role_fails(self):
        signed=self.signed()
        with self.assertRaises(SignatureError):
            self.verify(signed,reviewer_keys={})


if __name__=="__main__":
    unittest.main()
