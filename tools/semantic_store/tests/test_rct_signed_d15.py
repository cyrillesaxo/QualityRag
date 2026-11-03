"""Real Ed25519 policy/D15 signature verification; no self-attested evidence proof."""
import copy
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
from rct_signed_d15 import CELLS, proposed_d15_review,verify_d15_review
from store import digest

SOURCE="a"*64
CANDIDATE="b"*64
EVIDENCE="c"*64


def native_d15(*, failure=None, full=False):
    cells=[]
    for code in CELLS:
        status=("FAIL" if code==failure else "PASS" if full else "UNTESTED")
        refs=[f"evidence-{code}"] if status in ("PASS","FAIL") else []
        cells.append({"id":code,"status":status,"evidence_refs":refs})
    failed=[r["id"] for r in cells if r["status"]=="FAIL"]
    return {
        "schema":"qualityrag.native-d15-diagnostics/v1",
        "original_engine_schema":"apx.deception-census/v0.1",
        "cells":cells,
        "passed_cells":[r["id"] for r in cells if r["status"]=="PASS"],
        "failed_cells":failed,
        "inconclusive_cells":[r["id"] for r in cells if r["status"]=="INCONCLUSIVE"],
        "untested_cells":[r["id"] for r in cells if r["status"]=="UNTESTED"],
        "verdict":"REFUSE" if failed else "INCONCLUSIVE",
        "qualityrag_admission":"INCONCLUSIVE","can_generate":False,
        "compression_authorized":False,"semantic_completeness":"UNKNOWN",
    }


def registry(native):
    return {ref:EVIDENCE for cell in native["cells"] for ref in cell["evidence_refs"]}


class SignedD15EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.ir=constraint_ir()
        self.policy_key=Ed25519PrivateKey.generate()
        self.reviewer_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",service="quality",
            environment="test",sequence=3,issued_at=START,expires_at=END)
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.nonces=SQLiteNonceStore(Path(tmp.name)/"nonce.db")
        self.counter=0

    def signed(self,native, records=None):
        records=registry(native) if records is None else records
        draft=proposed_d15_review(
            native=native,source_sha256=SOURCE,candidate_sha256=CANDIDATE,
            reviewed_ir=self.ir,evidence_registry=records)
        draft["review_status"]="REVIEWED_FINITE_D15_CLAIMS"
        self.counter+=1
        return sign_attestation(
            [],{"d15_review":draft},self.reviewer_key,key_id="d15-review",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",nonce=f"d15-{self.counter}",
            issued_at=START,expires_at=END)

    def verify(self,native, signed, records=None, **overrides):
        args=dict(native=native,source_sha256=SOURCE,candidate_sha256=CANDIDATE,
                  reviewed_ir=self.ir,evidence_registry=(
                      registry(native) if records is None else records),
                  signed_policy=self.policy,signed_review=signed,
                  policy_keys={"policy":self.policy_key.public_key()},
                  reviewer_keys={"d15-review":self.reviewer_key.public_key()},
                  minimum_sequence=3,service="quality",environment="test",
                  as_of=NOW,nonce_accepted=self.nonces)
        args.update(overrides)
        return verify_d15_review(**args)

    def test_all_missing_cells_remain_unknown(self):
        native=native_d15()
        result=self.verify(native,self.signed(native))
        self.assertEqual(len(result["untested_cells"]),15)
        self.assertEqual(result["claimed_pass_count"],0)
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertFalse(result["compression_authorized"])

    def test_signed_all_pass_does_not_admit_or_compress(self):
        native=native_d15(full=True)
        result=self.verify(native,self.signed(native))
        self.assertEqual(result["claimed_pass_count"],15)
        self.assertEqual(result["semantic_completeness"],"UNKNOWN")
        self.assertEqual(result["independent_evidence_custody"],"NOT_ESTABLISHED")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(result["can_generate"])
        self.assertFalse(result["compression_authorized"])

    def test_signed_failure_refuses(self):
        native=native_d15(failure="DW_FRAME")
        result=self.verify(native,self.signed(native))
        self.assertEqual(result["failed_cells"],["DW_FRAME"])
        self.assertEqual(result["verdict"],"REFUSE")

    def test_missing_evidence_registry_entry_is_rejected(self):
        native=native_d15(failure="DD_CHANNEL")
        with self.assertRaisesRegex(ValueError,"exact content digest"):
            proposed_d15_review(native=native,source_sha256=SOURCE,
                candidate_sha256=CANDIDATE,reviewed_ir=self.ir,evidence_registry={})

    def test_evidence_digest_substitution_invalidates_review(self):
        native=native_d15(failure="DS_FRAME")
        signed=self.signed(native)
        forged={ref:"d"*64 for ref in registry(native)}
        with self.assertRaisesRegex(ValueError,"differs"):
            self.verify(native,signed,records=forged)

    def test_source_candidate_digest_substitution_invalidates_review(self):
        native=native_d15()
        signed=self.signed(native)
        with self.assertRaisesRegex(ValueError,"differs"):
            self.verify(native,signed,candidate_sha256="e"*64)

    def test_replay_is_rejected(self):
        native=native_d15()
        signed=self.signed(native)
        self.verify(native,signed)
        with self.assertRaises(SignatureError):
            self.verify(native,signed)

    def test_untrusted_reviewer_fails(self):
        native=native_d15()
        with self.assertRaises(SignatureError):
            self.verify(native,self.signed(native),reviewer_keys={})

    def test_forged_native_admission_rejected(self):
        native=native_d15(full=True)
        native["qualityrag_admission"]="ADMIT"
        with self.assertRaisesRegex(ValueError,"Untrusted native"):
            proposed_d15_review(native=native,source_sha256=SOURCE,
                candidate_sha256=CANDIDATE,reviewed_ir=self.ir,
                evidence_registry=registry(native))

    def test_duplicate_cells_and_self_inconsistent_counts_rejected(self):
        native=native_d15()
        native["cells"][1]=copy.deepcopy(native["cells"][0])
        with self.assertRaisesRegex(ValueError,"duplicate"):
            proposed_d15_review(native=native,source_sha256=SOURCE,
                candidate_sha256=CANDIDATE,reviewed_ir=self.ir,
                evidence_registry=registry(native))
        native=native_d15()
        native["untested_cells"]=[]
        with self.assertRaisesRegex(ValueError,"status lists"):
            proposed_d15_review(native=native,source_sha256=SOURCE,
                candidate_sha256=CANDIDATE,reviewed_ir=self.ir,
                evidence_registry=registry(native))

    def test_policy_rollback_rejected(self):
        native=native_d15()
        with self.assertRaises(SignatureError):
            self.verify(native,self.signed(native),minimum_sequence=4)


if __name__=="__main__":
    unittest.main()
