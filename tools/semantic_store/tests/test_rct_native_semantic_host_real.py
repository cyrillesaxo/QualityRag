"""Real original-APX => signed QualityRag research decision test.

The normal open-source CI skips this optional integration. The private native
APX workflow sets QR_REQUIRE_NATIVE_APX=1 and supplies actual compiled
apx-epistemic modules; absent native modules then FAIL instead of skipping.
"""
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy,sign_attestation
from signed_gate import SQLiteNonceStore
from rct_end_to_end import run_structural_pipeline,attach_source_span_conservation
from rct_signed_span_review import proposed_inventory_review
from rct_native_semantic_host import execute_dual_semantic_check
from test_rct_purpose_lens import fixture,grammar
from test_rct_source_span_conservation import item
from test_rct_signed_lineage import constraint_ir,START,NOW,END
from store import digest


@unittest.skipUnless(os.environ.get("QR_REQUIRE_NATIVE_APX")=="1",
                     "Native private APX execution requires an authenticated checkout")
class OriginalAPXHostEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.root=os.environ.get("APX_PACKAGES_ROOT")
        if not self.root:
            raise RuntimeError("Native APX workflow must provide APX_PACKAGES_ROOT")
        train,tlabels=fixture("train-")
        held,labels=fixture("held-")
        self.structural=run_structural_pipeline(
            train,tlabels,held,labels,grammar(),
            purpose="finite-classification-training",
            lens_id="native-host-integration",
            required_predicates=["p","q","r"],
            allowed_omission_predicates=["context"])
        self.ir=constraint_ir()
        self.policy_key=Ed25519PrivateKey.generate()
        self.reviewer_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",
            service="native-test",environment="test",
            sequence=1,issued_at=START,expires_at=END)
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.nonces=SQLiteNonceStore(Path(self.temp.name)/"signed-review-nonces.db")
        self.counter=0

    def run_case(self,source,candidate,source_quote,target_quote=None, *,
                 semantic_kind,expected,observed,expected_verdict):
        reviewed_obligations=[item(
            "critical-distinction",semantic_kind,source,candidate,
            source_quote,target_quote,required=True,
            value=expected,observed=observed)]
        joined=attach_source_span_conservation(
            self.structural,
            source_text=source,candidate_text=candidate,
            obligations=reviewed_obligations,
            source_digest=sha256(source.encode()).hexdigest(),
            candidate_digest=sha256(candidate.encode()).hexdigest(),
            reviewed_inventory_digest=digest(reviewed_obligations))
        inventory_review=proposed_inventory_review(joined,self.ir)
        inventory_review["review_status"]="REVIEWED_FINITE_SCOPE"
        self.counter+=1
        signed_review=sign_attestation(
            [],{"source_span_inventory_review":inventory_review},
            self.reviewer_key,key_id="reviewer",
            policy_signature=self.policy["signature"],
            service="native-test",environment="test",
            nonce="native-run-"+str(self.counter),
            issued_at=START,expires_at=END)
        result=execute_dual_semantic_check(
            joined, source_text=source,candidate_text=candidate,
            apx_packages_root=self.root,
            ir=self.ir,signed_policy=self.policy,
            signed_review=signed_review,
            policy_keys={"policy":self.policy_key.public_key()},
            reviewer_keys={"reviewer":self.reviewer_key.public_key()},
            minimum_sequence=1,
            service="native-test",environment="test",
            as_of=NOW,nonce_accepted=self.nonces)
        self.assertEqual(result["verdict"],expected_verdict)
        self.assertEqual(result["native_comparator_status"],
                         "REPORTED_BOUNDED_LEXICAL_CHECK")
        self.assertEqual(result["semantic_completeness"],"UNKNOWN")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")
        return result

    def test_real_apx_negation_reversal_and_signed_review(self):
        self.run_case(
            "The nurse must NOT administer the medication.",
            "The nurse must administer the medication.",
            "NOT",None,semantic_kind="NEGATION",
            expected="NEGATED",observed=None,
            expected_verdict="REFUSE")

    def test_real_apx_hvac_exception_and_signed_review(self):
        self.run_case(
            "Disconnect power unless a live diagnostic is required.",
            "Disconnect power.",
            "unless",None,semantic_kind="EXCEPTION",
            expected="CONDITIONAL",observed=None,
            expected_verdict="REFUSE")

    def test_real_apx_identical_text_never_semantic_admit(self):
        source="Refunds are allowed only if submitted within 30 days."
        self.run_case(
            source,source,
            "only if","only if",semantic_kind="CONDITION",
            expected="CONDITIONAL",observed="CONDITIONAL",
            expected_verdict="INCONCLUSIVE")


if __name__=="__main__":
    unittest.main()
