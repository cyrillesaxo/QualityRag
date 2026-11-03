"""Signed canonical 12G coverage review never infers source labels from text."""
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy,sign_attestation,SignatureError
from signed_gate import SQLiteNonceStore
from rct_end_to_end import run_structural_pipeline,attach_source_span_conservation
from rct_signed_span_review import proposed_inventory_review
from rct_reviewed_12g import propose_g_mapping,verify_reviewed_g_mapping,CODES
from test_rct_purpose_lens import fixture,grammar
from test_rct_source_span_conservation import item
from test_rct_signed_lineage import constraint_ir,START,NOW,END
from store import digest


class ReviewedCanonical12GTests(unittest.TestCase):
    def setUp(self):
        train,tlabels=fixture("train-")
        held,labels=fixture("held-")
        structural=run_structural_pipeline(
            train,tlabels,held,labels,grammar(),
            purpose="finite-classification-training",lens_id="canonical-12g",
            required_predicates=["p","q","r"],
            allowed_omission_predicates=["context"])
        source="The nurse must NOT administer the medication."
        candidate="The nurse must administer the medication."
        obligations=[item(
            "negation","NEGATION",source,candidate,
            "NOT","must",value="NEGATED",observed="AFFIRMATIVE")]
        self.joined=attach_source_span_conservation(
            structural,source_text=source,candidate_text=candidate,
            obligations=obligations,
            source_digest=sha256(source.encode()).hexdigest(),
            candidate_digest=sha256(candidate.encode()).hexdigest(),
            reviewed_inventory_digest=digest(obligations))
        self.ir=constraint_ir()
        # An explicit reviewer makes this *illustrative* boundary
        # classification; no automatic NOT -> G3 mapping exists.
        self.mapping=[{
            "code":code,"observed":code=="G3",
            "obligation_ids":["negation"] if code=="G3" else []}
            for code in CODES]
        self.policy_key=Ed25519PrivateKey.generate()
        self.span_key=Ed25519PrivateKey.generate()
        self.g_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",service="quality",
            environment="test",sequence=3,issued_at=START,expires_at=END)
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.nonces=SQLiteNonceStore(Path(temp.name)/"g-nonces.db")
        self.seq=0

    def signed_reviews(self,mapping=None):
        self.seq+=1
        signed_span=proposed_inventory_review(self.joined,self.ir)
        signed_span["review_status"]="REVIEWED_FINITE_SCOPE"
        span=sign_attestation(
            [],{"source_span_inventory_review":signed_span},
            self.span_key,key_id="span-reviewer",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce="span-"+str(self.seq),issued_at=START,expires_at=END)
        proposed=propose_g_mapping(
            self.joined,self.ir,self.mapping if mapping is None else mapping)
        proposed["review_status"]="REVIEWED_FINITE_COORDINATE_MAP"
        g=sign_attestation(
            [],{"rct_reviewed_g_map":proposed},
            self.g_key,key_id="g-reviewer",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce="g-"+str(self.seq),issued_at=START,expires_at=END)
        return span,g

    def verify(self,span,g,**overrides):
        params={
            "joined":self.joined,"ir":self.ir,"mapping":self.mapping,
            "signed_policy":self.policy,
            "signed_span_review":span,"signed_g_review":g,
            "policy_keys":{"policy":self.policy_key.public_key()},
            "span_reviewer_keys":{"span-reviewer":self.span_key.public_key()},
            "g_reviewer_keys":{"g-reviewer":self.g_key.public_key()},
            "minimum_sequence":3,"service":"quality","environment":"test",
            "as_of":NOW,"nonce_accepted":self.nonces}
        params.update(overrides)
        return verify_reviewed_g_mapping(**params)

    def test_real_cryptographic_review_covers_twelve_distinct_coordinates(self):
        span,g=self.signed_reviews()
        result=self.verify(span,g)
        self.assertEqual(len(result["coordinates"]),12)
        self.assertEqual([c["code"] for c in result["coordinates"]],list(CODES))
        self.assertEqual(result["coordinates"][2]["observed_status"],
                         "OBSERVED_VIOLATION")
        self.assertEqual(result["coordinates"][0]["observed_status"],"UNOBSERVED")
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")
        self.assertTrue(all(c["deltaRef"] is None for c in
                            result["canonical_rcoc_snapshot"]["coordinates"]))

    def test_unknown_g_code_and_incomplete_inventory_rejected(self):
        mapping=[dict(x) for x in self.mapping]
        mapping[0]["code"]="G13"
        with self.assertRaises(ValueError):
            propose_g_mapping(self.joined,self.ir,mapping)
        mapping=[dict(x) for x in self.mapping]
        mapping[2]["obligation_ids"]=[]
        with self.assertRaises(ValueError):
            propose_g_mapping(self.joined,self.ir,mapping)

    def test_reviewer_cannot_silently_reclassify_after_signing(self):
        span,g=self.signed_reviews()
        changed=[dict(x) for x in self.mapping]
        changed[2]={"code":"G3","observed":False,"obligation_ids":[]}
        changed[3]={"code":"G4","observed":True,"obligation_ids":["negation"]}
        with self.assertRaisesRegex(ValueError,"differs"):
            self.verify(span,g,mapping=changed)

    def test_same_g_review_replay_rejected(self):
        span,g=self.signed_reviews()
        self.verify(span,g)
        with self.assertRaises(SignatureError):
            self.verify(span,g)

    def test_forged_review_signature_rejected(self):
        span,g=self.signed_reviews()
        g["signature"]="A"*86
        with self.assertRaises(SignatureError):
            self.verify(span,g)

    def test_separate_role_key_required(self):
        span,g=self.signed_reviews()
        with self.assertRaises(SignatureError):
            self.verify(span,g,g_reviewer_keys={})

    def test_policy_source_substitution_rejected(self):
        span,g=self.signed_reviews()
        with self.assertRaises(SignatureError):
            self.verify(span,g,policy_keys={
                "policy":Ed25519PrivateKey.generate().public_key()})

    def test_unsigned_reviewed_mapping_cannot_be_admitted(self):
        draft=propose_g_mapping(self.joined,self.ir,self.mapping)
        self.assertEqual(draft["review_status"],"REVIEW_REQUIRED")
        self.assertEqual(draft["semantic_completeness"],"UNKNOWN")
        self.assertEqual(draft["unobserved_coordinates"],
                         "NOT_PROVEN_NOT_APPLICABLE")


if __name__=="__main__":
    unittest.main()
