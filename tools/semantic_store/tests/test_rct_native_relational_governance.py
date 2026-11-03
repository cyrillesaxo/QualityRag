"""Composed signed role/lexical/span governance: native API isolated by mock.

These tests verify the Python trust orchestration with real Ed25519 and durable
nonces. They do NOT count as an execution of the separately built original
private APX binary; original-engine coverage has its own native workflow.
"""
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy,sign_attestation,SignatureError
from signed_gate import SQLiteNonceStore
from rct_end_to_end import run_structural_pipeline,attach_source_span_conservation
from rct_signed_span_review import proposed_inventory_review
from rct_signed_role_grammar import proposed_role_review
from rct_native_semantic_host import execute_relational_semantic_check
from test_rct_purpose_lens import fixture,grammar
from test_rct_signed_lineage import constraint_ir,START,NOW,END
from test_rct_source_span_conservation import item
from test_rct_role_grammar import fact
from store import digest


class RelationalNativeGovernanceTests(unittest.TestCase):
    def setUp(self):
        train,tlabels=fixture("train-")
        held,labels=fixture("held-")
        self.structural=run_structural_pipeline(
            train,tlabels,held,labels,grammar(),
            purpose="finite-classification-training",
            lens_id="native-relational-integration",
            required_predicates=["p","q","r"],
            allowed_omission_predicates=["context"])
        self.ir=constraint_ir()
        self.policy_key=Ed25519PrivateKey.generate()
        self.span_key=Ed25519PrivateKey.generate()
        self.role_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(
            self.ir,self.policy_key,key_id="policy",
            service="quality",environment="test",
            sequence=4,issued_at=START,expires_at=END)
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.nonces=SQLiteNonceStore(Path(temp.name)/"nonce.db")
        self.counter=0

    def prepare(self,source="Alice must pay Bob.",
                candidate="Bob must pay Alice.", *, same_roles=False):
        obligation=[item("modal","MODALITY",source,candidate,
                         "must","must",
                         value="REQUIRED",observed="REQUIRED")]
        joined=attach_source_span_conservation(
            self.structural,source_text=source,candidate_text=candidate,
            obligations=obligation,
            source_digest=sha256(source.encode()).hexdigest(),
            candidate_digest=sha256(candidate.encode()).hexdigest(),
            reviewed_inventory_digest=digest(obligation))
        before=[fact(source,"payment","PAY",
                     OBLIGOR=("alice","Alice"),
                     BENEFICIARY=("bob","Bob"))]
        after=[fact(candidate,"payment","PAY",
                    OBLIGOR=("alice" if same_roles else "bob",
                             "Alice" if same_roles else "Bob"),
                    BENEFICIARY=("bob" if same_roles else "alice",
                                 "Bob" if same_roles else "Alice"))]
        self.counter+=1
        n=self.counter
        span_draft=proposed_inventory_review(joined,self.ir)
        span_draft["review_status"]="REVIEWED_FINITE_SCOPE"
        role_draft=proposed_role_review(
            source=source,candidate=candidate,
            source_facts=before,candidate_facts=after,ir=self.ir)
        role_draft["review_status"]="REVIEWED_FINITE_ROLE_BINDINGS"
        span_signed=sign_attestation(
            [],{"source_span_inventory_review":span_draft},
            self.span_key,key_id="span-reviewer",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce=f"span-{n}",issued_at=START,expires_at=END)
        role_signed=sign_attestation(
            [],{"typed_role_graph_review":role_draft},
            self.role_key,key_id="role-reviewer",
            policy_signature=self.policy["signature"],
            service="quality",environment="test",
            nonce=f"role-{n}",issued_at=START,expires_at=END)
        return dict(
            joined=joined,source_text=source,candidate_text=candidate,
            source_facts=before,candidate_facts=after,
            apx_packages_root="/trusted/apx/packages",
            ir=self.ir,signed_policy=self.policy,
            signed_span_review=span_signed,signed_role_review=role_signed,
            policy_keys={"policy":self.policy_key.public_key()},
            span_reviewer_keys={"span-reviewer":self.span_key.public_key()},
            role_reviewer_keys={"role-reviewer":self.role_key.public_key()},
            minimum_sequence=4,service="quality",environment="test",
            as_of=NOW,nonce_accepted=self.nonces)

    def mock_native(self,params,verdict="INCONCLUSIVE"):
        return {
            "schema":"qualityrag.native-semantic-transition/v1",
            "original_engine_schema":"apx.semantic-text-transition/v0.1",
            "source_sha256":sha256(params["source_text"].encode()).hexdigest(),
            "candidate_sha256":sha256(params["candidate_text"].encode()).hexdigest(),
            "verdict":verdict,"observed_changes":[],
            "source_authority":"UNVERIFIED_HEURISTIC",
            "source_coverage":"BOUNDED_ENGLISH_PATTERNS",
            "semantic_completeness":"UNKNOWN",
            "qualityrag_admission":"INCONCLUSIVE",
            "can_generate":False,
        }

    def test_signed_role_inversion_refuses_when_lexical_engine_abstains(self):
        args=self.prepare()
        with patch("rct_native_semantic_host.inspect_native_semantics",
                   return_value=self.mock_native(args)) as native:
            receipt=execute_relational_semantic_check(**args)
        native.assert_called_once()
        self.assertEqual(receipt["native_lexical_verdict"],"INCONCLUSIVE")
        self.assertEqual(receipt["signed_span_verdict"],"INCONCLUSIVE")
        self.assertEqual(receipt["signed_role_verdict"],"REFUSE")
        self.assertEqual(receipt["verdict"],"REFUSE")
        self.assertFalse(receipt["can_generate"])
        self.assertEqual(receipt["semantic_completeness"],"UNKNOWN")

    def test_same_reviewed_roles_still_inconclusive(self):
        args=self.prepare(candidate="Bob must be paid by Alice.",same_roles=True)
        with patch("rct_native_semantic_host.inspect_native_semantics",
                   return_value=self.mock_native(args)):
            receipt=execute_relational_semantic_check(**args)
        self.assertEqual(receipt["verdict"],"INCONCLUSIVE")
        self.assertEqual(receipt["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(receipt["can_generate"])

    def test_changed_role_annotation_fails_before_native(self):
        args=self.prepare()
        args["candidate_facts"][0]["bindings"][0]["entity"]="alice"
        with patch("rct_native_semantic_host.inspect_native_semantics") as native:
            with self.assertRaisesRegex(ValueError,"Signed role"):
                execute_relational_semantic_check(**args)
        native.assert_not_called()

    def test_bad_span_signature_fails_before_native(self):
        args=self.prepare()
        args["signed_span_review"]["signature"]="A"*86
        with patch("rct_native_semantic_host.inspect_native_semantics") as native:
            with self.assertRaises(SignatureError):
                execute_relational_semantic_check(**args)
        native.assert_not_called()

    def test_document_substitution_fails_before_native(self):
        args=self.prepare()
        args["source_text"]="Eve must pay Bob."
        with patch("rct_native_semantic_host.inspect_native_semantics") as native:
            with self.assertRaisesRegex(ValueError,"reviewed documents"):
                execute_relational_semantic_check(**args)
        native.assert_not_called()

    def test_two_reviewers_must_be_distinct(self):
        args=self.prepare()
        args["signed_role_review"]["key_id"]=args["signed_span_review"]["key_id"]
        with patch("rct_native_semantic_host.inspect_native_semantics") as native:
            with self.assertRaisesRegex(ValueError,"Independent"):
                execute_relational_semantic_check(**args)
        native.assert_not_called()

    def test_replay_is_rejected(self):
        args=self.prepare()
        with patch("rct_native_semantic_host.inspect_native_semantics",
                   return_value=self.mock_native(args)):
            execute_relational_semantic_check(**args)
            with self.assertRaises(SignatureError):
                execute_relational_semantic_check(**args)


if __name__=="__main__":
    unittest.main()
