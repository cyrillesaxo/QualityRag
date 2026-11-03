"""Dual semantic checks verify a real signed policy/review on every call.

Uses actual Ed25519 and durable nonce ledger. The native observation
responses in this suite are interface fixtures; original APX execution is
tested separately in the opt-in private native workflow.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_attestation,sign_policy,SignatureError
from signed_gate import SQLiteNonceStore
from store import digest
from rct_dual_semantic import combine_semantic_diagnostics
from rct_signed_span_review import proposed_inventory_review
from test_rct_signed_lineage import constraint_ir,START,NOW,END


def joined_shape(verdict="INCONCLUSIVE"):
    audit={"schema":"rct.source-span-conservation/v2.1",
           "source_sha256":"a"*64, "candidate_sha256":"b"*64,
           "reviewed_inventory_sha256":"c"*64,
           "qualityrag_admission":"INCONCLUSIVE",
           "verdict":verdict}
    audit["fingerprint"]=digest(audit)
    joined={"schema":"rct.source-span-joined-candidate/v2.1",
            "source_span_audit":audit,"verdict":verdict,
            "qualityrag_admission":"INCONCLUSIVE","can_generate":False}
    joined["fingerprint"]=digest(joined)
    return joined


def native_shape(verdict="INCONCLUSIVE"):
    return {
        "schema":"qualityrag.native-semantic-transition/v1",
        "original_engine_schema":"apx.semantic-text-transition/v0.1",
        "source_sha256":"a"*64,"candidate_sha256":"b"*64,
        "source_authority":"UNVERIFIED_HEURISTIC",
        "semantic_completeness":"UNKNOWN",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,"observed_changes":[],
        "verdict":verdict,
    }


class DualSemanticTest(unittest.TestCase):
    def setUp(self):
        self.ir=constraint_ir()
        self.joined=joined_shape()
        self.policy_key=Ed25519PrivateKey.generate()
        self.review_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",service="quality",
            environment="test",sequence=2,issued_at=START,expires_at=END)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nonces=SQLiteNonceStore(Path(self.tmp.name)/"nonces.db")
        self.counter=0

    def sign(self,joined=None):
        record=proposed_inventory_review(
            self.joined if joined is None else joined,self.ir)
        record["review_status"]="REVIEWED_FINITE_SCOPE"
        self.counter+=1
        return sign_attestation(
            [],{"source_span_inventory_review":record},
            self.review_key,key_id="reviewer",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce="dual-semantic-"+str(self.counter),
            issued_at=START,expires_at=END)

    def run_check(self,native=None,**overrides):
        args={
            "joined":self.joined,"native":native,
            "ir":self.ir,"signed_policy":self.policy,
            "signed_review":self.sign(),
            "policy_keys":{"policy":self.policy_key.public_key()},
            "reviewer_keys":{"reviewer":self.review_key.public_key()},
            "minimum_sequence":2,
            "service":"quality","environment":"test",
            "as_of":NOW,"nonce_accepted":self.nonces}
        args.update(overrides)
        return combine_semantic_diagnostics(**args)

    def test_unchanged_observations_cannot_admit(self):
        output=self.run_check(native_shape())
        self.assertEqual(output["verdict"],"INCONCLUSIVE")
        self.assertEqual(output["native_comparator_status"],
                         "REPORTED_BOUNDED_LEXICAL_CHECK")
        self.assertFalse(output["can_generate"])
        self.assertEqual(output["semantic_completeness"],"UNKNOWN")
        self.assertEqual(output["qualityrag_admission"],"INCONCLUSIVE")

    def test_native_observed_drift_refuses(self):
        self.assertEqual(self.run_check(native_shape("REFUSE"))["verdict"],"REFUSE")

    def test_reviewed_source_refusal_dominates_native(self):
        j=joined_shape("REFUSE")
        self.assertEqual(self.run_check(native_shape(),
            joined=j,signed_review=self.sign(j))["verdict"],"REFUSE")

    def test_missing_original_engine_is_unresolved(self):
        output=self.run_check()
        self.assertEqual(output["verdict"],"INCONCLUSIVE")
        self.assertIn("NATIVE_APX_SOURCE_COMPARATOR_NOT_EXECUTED",
                      output["blockers"])

    def test_wrong_document_digest_is_rejected(self):
        forged=native_shape()
        forged["source_sha256"]="d"*64
        with self.assertRaisesRegex(ValueError,"exact document versions"):
            self.run_check(forged)

    def test_review_signature_cannot_be_forged(self):
        with self.assertRaises(SignatureError):
            self.run_check(native_shape(),reviewer_keys={
                "reviewer":Ed25519PrivateKey.generate().public_key()})

    def test_stale_source_version_invalidates_review(self):
        changed=joined_shape()
        changed["source_span_audit"]["source_sha256"]="d"*64
        changed["source_span_audit"]["fingerprint"]=digest({
            k:v for k,v in changed["source_span_audit"].items()
            if k!="fingerprint"})
        changed["fingerprint"]=digest({
            k:v for k,v in changed.items() if k!="fingerprint"})
        with self.assertRaisesRegex(ValueError,"exact inventory"):
            self.run_check(native_shape(),joined=changed)

    def test_review_attestation_replay_fails(self):
        signed=self.sign()
        self.run_check(native_shape(),signed_review=signed)
        with self.assertRaises(SignatureError):
            self.run_check(native_shape(),signed_review=signed)

    def test_pack_policy_signature_mismatch_rejected(self):
        with self.assertRaises(SignatureError):
            self.run_check(native_shape(),policy_keys={
                "policy":Ed25519PrivateKey.generate().public_key()})


if __name__=="__main__":
    unittest.main()
