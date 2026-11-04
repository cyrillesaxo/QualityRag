"""Pilot approvals bind the actual candidate, target and host policy before replay use."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import review_binding
from tools.activation_runtime.release import REQUIRED,readiness,approval_context,authorize_release
from signed_gate import SQLiteNonceStore

AT="2026-11-04T12:00:00Z"


class ReleaseAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.nonce_path=Path(self.temp.name)/"nonces.sqlite"
        self.nonces=SQLiteNonceStore(self.nonce_path)
        self.author=Ed25519PrivateKey.generate();self.reviewer=Ed25519PrivateKey.generate()
        self.evidence={key:{"receipt_sha256":"a"*64,"status":"INDEPENDENTLY_VERIFIED"} for key in REQUIRED}
        self.context={key:"b"*64 for key in ("source_sha256","artifact_sha256","policy_ir_sha256","grammar_sha256","model_sha256","decoder_sha256")}
        self.context.update(run_id="fixture-run",sequence=3,service="fixture-service",environment="test-pilot")

    def bound(self,**changes):
        args=dict(critical_field_failures=0,total_cost_comparison="MEASURED_NO_CROSSOVER",context=self.context,tenant="fixture",minimum_sequence=1)
        args.update(changes)
        return approval_context(self.evidence,**args)

    def signed(self,context=None,*,key=None,reviewer="assigned-reviewer"):
        return review_binding(context or self.bound(),decision="APPROVE",reviewer=reviewer,author_key_id="author",
            key=key or self.reviewer,key_id="release-key",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="release-once")

    def authorize(self,envelope=None,**changes):
        args=dict(critical_field_failures=0,total_cost_comparison="MEASURED_NO_CROSSOVER",context=self.context,
            signed_review=envelope or self.signed(),reviewer_keys={"release-key":self.reviewer.public_key()},
            reviewer_subjects={"release-key":"assigned-reviewer"},author_public_key=self.author.public_key(),as_of=AT,
            nonce_store=self.nonces,tenant="fixture",minimum_sequence=1)
        args.update(changes)
        return authorize_release(self.evidence,**args)

    def count(self):
        with sqlite3.connect(self.nonce_path) as db:return db.execute("SELECT count(*) FROM used_nonce").fetchone()[0]

    def test_valid_signed_approval_is_bound_research_pilot_not_production_or_truth(self):
        result=self.authorize()
        self.assertTrue(result["can_release"])
        self.assertEqual(result["approved_context"],self.bound())
        self.assertEqual(result["release_scope"],"RESEARCH_PILOT_ONLY")
        self.assertFalse(result["can_release_production"])
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["economic_outcome"],"MEASURED_NO_CROSSOVER")

    def test_each_source_runtime_target_and_version_change_invalidates_review(self):
        signed=self.signed()
        changes={key:"c"*64 for key in ("source_sha256","artifact_sha256","policy_ir_sha256","grammar_sha256","model_sha256","decoder_sha256")}
        changes.update(run_id="other-run",sequence=4,service="other-service",environment="other-pilot")
        for key,value in changes.items():
            with self.subTest(field=key):
                with self.assertRaises(PermissionError):self.authorize(signed,context={**self.context,key:value})
                self.assertEqual(self.count(),0)
        self.authorize(signed)

    def test_approval_cannot_cross_tenant_economic_outcome_or_version_policy(self):
        signed=self.signed()
        for changes in ({"tenant":"other"},{"total_cost_comparison":"MEASURED_ADVANTAGE"},{"minimum_sequence":2}):
            with self.subTest(fields=list(changes)):
                with self.assertRaises(PermissionError):self.authorize(signed,**changes)
                self.assertEqual(self.count(),0)
        self.authorize(signed)

    def test_missing_or_extra_manifest_fields_never_authorize(self):
        signed=self.signed()
        for field in self.context:
            missing={key:value for key,value in self.context.items() if key!=field}
            with self.assertRaises(ValueError):self.authorize(signed,context=missing)
        with self.assertRaises(ValueError):self.authorize(signed,context={**self.context,"unreviewed":"option"})
        self.assertEqual(self.count(),0)

    def test_invalid_hashes_counts_and_downgrade_refuse_before_nonce_use(self):
        for value in ("z"*64,"b"*63,None,True):
            with self.assertRaises(ValueError):self.authorize(context={**self.context,"model_sha256":value})
        for floor in (0,-1,True):
            with self.assertRaises(ValueError):self.authorize(minimum_sequence=floor)
        with self.assertRaises(ValueError):self.authorize(minimum_sequence=4)
        self.assertEqual(self.count(),0)

    def test_wrong_subject_or_incomplete_subject_map_cannot_burn_approval(self):
        signed=self.signed()
        for subjects in ({},{"release-key":"other"},None):
            with self.assertRaises(PermissionError):self.authorize(signed,reviewer_subjects=subjects)
            self.assertEqual(self.count(),0)
        self.authorize(signed)

    def test_signer_cannot_impersonate_another_host_subject(self):
        with self.assertRaises(PermissionError):self.authorize(self.signed(reviewer="other"))
        self.assertEqual(self.count(),0)

    def test_expired_revoked_and_same_author_key_aliases_refuse(self):
        signed=self.signed()
        with self.assertRaises(ValueError):self.authorize(signed,as_of="2026-11-06T00:00:00Z")
        with self.assertRaises(ValueError):self.authorize(signed,reviewer_keys={},reviewer_subjects={})
        with self.assertRaises(PermissionError):self.authorize(self.signed(key=self.author),reviewer_keys={"release-key":self.author.public_key()})
        self.assertEqual(self.count(),0)

    def test_receipt_evidence_change_invalidates_old_review(self):
        signed=self.signed();self.evidence["telemetry"]["receipt_sha256"]="c"*64
        with self.assertRaises(PermissionError):self.authorize(signed)
        self.assertEqual(self.count(),0)

    def test_bad_evidence_hashes_block_instead_of_raising_type_errors(self):
        for value in (None,42,True,"z"*64,"a"*63):
            with self.subTest(value=value):
                evidence=deepcopy(self.evidence);evidence["security_review"]["receipt_sha256"]=value
                result=readiness(evidence,critical_field_failures=0,total_cost_comparison="MEASURED_NO_CROSSOVER")
                self.assertEqual(result["decision"],"BLOCK")
                self.assertIn("security_review",result["blockers"])

    def test_critical_loss_or_unknown_economics_block_without_consuming_nonce(self):
        for changes in ({"critical_field_failures":1},{"total_cost_comparison":"UNKNOWN"}):
            result=self.authorize(**changes)
            self.assertFalse(result["can_release"])
            self.assertEqual(self.count(),0)

    def test_replay_refuses_after_success(self):
        signed=self.signed();self.authorize(signed)
        with self.assertRaises(PermissionError):self.authorize(signed)
        self.assertEqual(self.count(),1)

    def test_legacy_unbound_release_context_is_not_grandfathered(self):
        legacy={"release_evidence_sha256":readiness(self.evidence,critical_field_failures=0,
            total_cost_comparison="MEASURED_NO_CROSSOVER")["evidence_sha256"],"economic_outcome":"MEASURED_NO_CROSSOVER"}
        with self.assertRaises(PermissionError):self.authorize(self.signed(context=legacy))
        self.assertEqual(self.count(),0)
