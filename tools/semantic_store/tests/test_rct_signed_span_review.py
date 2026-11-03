"""Real Ed25519 review of versioned source-span inventories and PackSpec nodes."""
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy, sign_attestation, SignatureError
from signed_gate import SQLiteNonceStore
from rct_end_to_end import run_structural_pipeline, attach_source_span_conservation
from rct_signed_span_review import proposed_inventory_review, verify_inventory_review
from test_rct_source_span_conservation import item
from test_rct_purpose_lens import fixture, grammar
from test_rct_signed_lineage import constraint_ir, START, NOW, END
from store import digest


class SignedSpanInventoryReviewTests(unittest.TestCase):
    def setUp(self):
        train,train_labels=fixture("train-")
        held,labels=fixture("held-")
        self.structural=run_structural_pipeline(
            train,train_labels,held,labels,grammar(),
            purpose="training",lens_id="review-typed-source",
            required_predicates=["p","q","r"],
            allowed_omission_predicates=["context"])
        self.source="A nurse must NOT administer this medication."
        self.candidate="A nurse must administer this medication."
        self.inventory=[item("negation","NEGATION",self.source,self.candidate,
                             "NOT","must",value="NEGATED",observed="AFFIRMATIVE")]
        self.joined=attach_source_span_conservation(
            self.structural,source_text=self.source,candidate_text=self.candidate,
            obligations=self.inventory,
            source_digest=sha256(self.source.encode()).hexdigest(),
            candidate_digest=sha256(self.candidate.encode()).hexdigest(),
            reviewed_inventory_digest=digest(self.inventory))
        self.ir=constraint_ir()
        self.policy_key=Ed25519PrivateKey.generate()
        self.reviewer_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",service="quality",
            environment="test",sequence=4,issued_at=START,expires_at=END)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nonce=SQLiteNonceStore(Path(self.tmp.name)/"review-nonces.db")
        self.counter=0

    def signed(self, record=None):
        self.counter+=1
        if record is None:
            record=proposed_inventory_review(self.joined,self.ir)
            record["review_status"]="REVIEWED_FINITE_SCOPE"
        return sign_attestation(
            [],{"source_span_inventory_review":record},self.reviewer_key,
            key_id="reviewer",policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce="signed-span-"+str(self.counter),
            issued_at=START,expires_at=END)

    def evaluate(self,signed_review,**changes):
        args={
            "joined":self.joined,"ir":self.ir,
            "signed_policy":self.policy,"signed_review":signed_review,
            "policy_keys":{"policy":self.policy_key.public_key()},
            "reviewer_keys":{"reviewer":self.reviewer_key.public_key()},
            "minimum_sequence":4,"service":"quality","environment":"test",
            "as_of":NOW,"nonce_accepted":self.nonce,
        }
        args.update(changes)
        return verify_inventory_review(**args)

    def test_signed_adversarial_refusal_remains_nonadmitted(self):
        result=self.evaluate(self.signed())
        self.assertEqual(result["review_signature"],"VERIFIED")
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["completeness"],"UNKNOWN")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_inventory_version_substitution_rejected(self):
        modified=dict(self.joined)
        audit=dict(modified["source_span_audit"])
        audit["reviewed_inventory_sha256"]="0"*64
        audit["fingerprint"]=digest({k:v for k,v in audit.items() if k!="fingerprint"})
        modified["source_span_audit"]=audit
        modified["fingerprint"]=digest({k:v for k,v in modified.items() if k!="fingerprint"})
        with self.assertRaisesRegex(ValueError,"exact inventory"):
            self.evaluate(self.signed(),joined=modified)

    def test_unsigned_pack_change_rejected(self):
        changed=dict(self.ir,ir_sha256="0"*64)
        with self.assertRaises(ValueError):
            self.evaluate(self.signed(),ir=changed)

    def test_policy_signature_replaced_rejected(self):
        other=Ed25519PrivateKey.generate()
        with self.assertRaises(SignatureError):
            self.evaluate(self.signed(),policy_keys={"policy":other.public_key()})

    def test_reviewer_signature_tamper_rejected(self):
        signed=self.signed()
        signed["signature"]="A"*86
        with self.assertRaises(SignatureError):
            self.evaluate(signed)

    def test_replay_rejected(self):
        signed=self.signed()
        self.evaluate(signed)
        with self.assertRaises(SignatureError):
            self.evaluate(signed)

    def test_missing_reviewer_identity_rejected(self):
        with self.assertRaises(SignatureError):
            self.evaluate(self.signed(),reviewer_keys={})

    def test_signed_review_cannot_overstate_completeness(self):
        draft=proposed_inventory_review(self.joined,self.ir)
        draft["review_status"]="REVIEWED_FINITE_SCOPE"
        draft["completeness"]="COMPLETE"
        with self.assertRaisesRegex(ValueError,"exact inventory"):
            self.evaluate(self.signed(draft))


if __name__=="__main__":
    unittest.main()
