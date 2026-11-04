"""Real signatures and SQLite transactions govern observed holdout openings."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import review_binding
from tools.activation_runtime.common import canonical,fingerprint
from tools.activation_runtime.experiments import Registry,paired_interval

AT="2026-11-04T12:00:00Z"


class HoldoutAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"registry.sqlite"
        self.author=Ed25519PrivateKey.generate();self.evaluator=Ed25519PrivateKey.generate()
        self.now=AT
        self.protocol=json.loads((Path(__file__).resolve().parents[1]/"research"/"protocol.json").read_text())
        self.protocol.update(dataset_sha256="a"*64,registered_at=AT)
        self.registry=self.create()

    def create(self,path=None,**changes):
        options=dict(registry_id="fixture-registry",tenant="fixture",reviewer_keys={"eval-key":self.evaluator.public_key()},
            reviewer_subjects={"eval-key":"evaluator"},author_public_key=self.author.public_key(),clock=lambda:self.now)
        options.update(changes)
        registry=Registry(path or self.path,**options)
        self.addCleanup(registry.close)
        return registry

    def grant(self,*,protocol_id=None,context=None,key=None,key_id="eval-key",reviewer="evaluator",nonce="once"):
        context=context or self.registry.holdout_context(protocol_id or self.protocol["id"],actor=reviewer,dataset_sha256="a"*64)
        return review_binding(context,decision="APPROVE",reviewer=reviewer,author_key_id="author",
            key=key or self.evaluator,key_id=key_id,issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce=nonce)

    def open(self,grant,registry=None,protocol_id=None,**changes):
        options=dict(actor="evaluator",dataset_sha256="a"*64,signed_review=grant)
        options.update(changes)
        return (registry or self.registry).open_holdout(protocol_id or self.protocol["id"],**options)

    def count(self,table="experiment_holdout_receipts"):
        return self.registry.db.execute("SELECT count(*) FROM "+table).fetchone()[0]

    def test_role_string_and_empty_envelope_cannot_authorize(self):
        self.registry.register(self.protocol)
        with self.assertRaises(TypeError):
            self.registry.open_holdout(self.protocol["id"],actor="proposer",role="independent-evaluator",dataset_sha256="a"*64)
        with self.assertRaises((ValueError,PermissionError)):self.open({})
        self.assertEqual(self.count(),0)
        self.open(self.grant())

    def test_grant_binds_purpose_actor_registry_tenant_and_dataset(self):
        self.registry.register(self.protocol)
        original=self.registry.holdout_context(self.protocol["id"],actor="evaluator",dataset_sha256="a"*64)
        for changes in ({"purpose":"OTHER"},{"tenant":"other"},{"registry_id":"other"},{"actor":"other"},
                        {"dataset_sha256":"b"*64},{"registration_sha256":"b"*64},{"protocol_sha256":"b"*64}):
            with self.subTest(fields=list(changes)):
                with self.assertRaises(PermissionError):self.open(self.grant(context={**original,**changes}))
                self.assertEqual(self.count(),0)
        with self.assertRaises(ValueError):self.open(self.grant(),dataset_sha256="b"*64)
        self.open(self.grant())

    def test_author_key_alias_cannot_act_as_independent_evaluator(self):
        self.registry.register(self.protocol)
        alias=self.create(reviewer_keys={"alias":self.author.public_key()},reviewer_subjects={"alias":"evaluator"})
        grant=self.grant(key=self.author,key_id="alias")
        with self.assertRaises(PermissionError):self.open(grant,registry=alias)
        self.assertEqual(self.count(),0)

    def test_authorized_key_cannot_choose_another_subject(self):
        self.registry.register(self.protocol)
        with self.assertRaises(PermissionError):self.open(self.grant(reviewer="other"),actor="other")
        self.assertEqual(self.count(),0)

    def test_expired_or_untrusted_grant_does_not_consume_nonce(self):
        self.registry.register(self.protocol)
        grant=self.grant();self.now="2026-11-06T12:00:00Z"
        with self.assertRaises(ValueError):self.open(grant)
        self.now=AT
        other=self.create(reviewer_keys={"eval-key":self.author.public_key()})
        with self.assertRaises(ValueError):self.open(grant,registry=other)
        revoked=self.create(reviewer_keys={},reviewer_subjects={})
        with self.assertRaises(ValueError):self.open(grant,registry=revoked)
        self.assertEqual(self.count(),0)
        self.open(grant)

    def test_opening_receipt_is_immutable_and_survives_restart(self):
        self.registry.register(self.protocol)
        grant=self.grant();self.assertEqual(self.open(grant),self.protocol)
        receipt=self.registry.opening_receipt(self.protocol["id"])
        self.assertEqual(receipt["review_envelope"],grant)
        self.assertEqual(receipt["context"]["dataset_sha256"],"a"*64)
        self.assertEqual(receipt["opened_at"],AT)
        for table in ("experiment_protocols","experiment_opens","experiment_registrations","experiment_holdout_receipts"):
            with self.assertRaises(sqlite3.IntegrityError):self.registry.db.execute("DELETE FROM "+table)
            self.registry.db.rollback()
        self.registry.close();reopened=self.create()
        self.assertEqual(reopened.opening_receipt(self.protocol["id"]),receipt)
        with self.assertRaises(PermissionError):self.open(grant,registry=reopened)

    def test_failure_after_nonce_reservation_rolls_back_opening(self):
        self.registry.register(self.protocol);grant=self.grant()
        self.registry.db.execute("CREATE TRIGGER injected_open_failure BEFORE INSERT ON experiment_opens BEGIN SELECT RAISE(ABORT,'fixture write failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.open(grant)
        self.assertEqual(self.count(),0);self.assertEqual(self.count("experiment_opens"),0)
        self.registry.db.execute("DROP TRIGGER injected_open_failure")
        self.open(grant)

    def test_outer_rollback_preserves_approval_reuse(self):
        self.registry.register(self.protocol);grant=self.grant()
        self.registry.db.execute("BEGIN IMMEDIATE")
        self.open(grant)
        self.assertTrue(self.registry.db.in_transaction)
        self.registry.db.rollback()
        self.assertEqual(self.count(),0);self.assertEqual(self.count("experiment_opens"),0)
        self.open(grant)

    def test_nonce_cannot_be_reused_for_another_protocol(self):
        self.registry.register(self.protocol);self.open(self.grant())
        other={**self.protocol,"id":self.protocol["id"]+"-second"};self.registry.register(other)
        with self.assertRaises(PermissionError):self.open(self.grant(protocol_id=other["id"]),protocol_id=other["id"])
        self.assertEqual(self.count(),1)

    def test_concurrent_openings_cannot_reuse_a_grant_nonce(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.registry.register(self.protocol)
        other={**self.protocol,"id":self.protocol["id"]+"-concurrent"};self.registry.register(other)
        ids=[self.protocol["id"],other["id"]]
        grants=[self.grant(protocol_id=pid) for pid in ids]
        barrier=Barrier(2)
        def worker(index):
            registry=Registry(self.path,registry_id="fixture-registry",tenant="fixture",
                reviewer_keys={"eval-key":self.evaluator.public_key()},reviewer_subjects={"eval-key":"evaluator"},
                author_public_key=self.author.public_key(),clock=lambda:AT)
            try:
                barrier.wait(timeout=10)
                try:
                    registry.open_holdout(ids[index],actor="evaluator",dataset_sha256="a"*64,signed_review=grants[index])
                    return True
                except PermissionError:return False
            finally:registry.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(self.count(),1)
        self.assertEqual(self.count("experiment_opens"),1)

    def test_future_invalid_hash_and_duplicate_arms_refuse_registration(self):
        for changes in ({"registered_at":"2026-11-05T12:00:00Z"},{"registered_at":"2026-11-04T12:00:00"},
                        {"dataset_sha256":"z"*64},{"arms":self.protocol["arms"]+["av1"]},{"sample_plan":True}):
            with self.subTest(fields=list(changes)):
                with self.assertRaises(ValueError):self.registry.register({**self.protocol,**changes})
        self.assertEqual(self.count("experiment_protocols"),0)

    def test_clock_cannot_rewind_before_observed_registration(self):
        self.registry.register(self.protocol);grant=self.grant();self.now="2026-11-04T11:59:59Z"
        with self.assertRaises(ValueError):self.open(grant)
        self.assertEqual(self.count(),0);self.now=AT;self.open(grant)

    def test_legacy_unobserved_registration_does_not_get_grandfathered(self):
        with self.registry.db:
            self.registry.db.execute("INSERT INTO experiment_protocols VALUES(?,?,?)",(self.protocol["id"],canonical(self.protocol).decode(),fingerprint(self.protocol)))
        with self.assertRaisesRegex(ValueError,"legacy"):
            self.registry.holdout_context(self.protocol["id"],actor="evaluator",dataset_sha256="a"*64)

    def test_changed_protocol_body_cannot_keep_its_old_fingerprint(self):
        self.registry.register(self.protocol);grant=self.grant()
        self.registry.db.execute("DROP TRIGGER experiment_protocols_update")
        changed={**self.protocol,"dataset_sha256":"b"*64}
        with self.registry.db:
            self.registry.db.execute("UPDATE experiment_protocols SET body=? WHERE id=?",(canonical(changed).decode(),self.protocol["id"]))
        with self.assertRaisesRegex(ValueError,"integrity"):self.open(grant)

    def test_grant_cannot_cross_registry_identity(self):
        self.registry.register(self.protocol);grant=self.grant()
        other=self.create(Path(self.temp.name)/"other.sqlite",registry_id="other-registry")
        other.register(self.protocol)
        with self.assertRaises(PermissionError):self.open(grant,registry=other)
        self.assertEqual(other.db.execute("SELECT count(*) FROM experiment_opens").fetchone()[0],0)

    def test_registry_requires_durable_database_and_host_subject_map(self):
        with self.assertRaisesRegex(ValueError,"Durable"):self.create(":memory:")
        with self.assertRaisesRegex(ValueError,"subject"):self.create(reviewer_subjects={})


class StatisticalBudgetTests(unittest.TestCase):
    def test_invalid_seeds_and_resampling_counts_fail_before_work(self):
        for count in (0,-1,True,99,10001,1.5):
            with self.assertRaises(ValueError):paired_interval([1,2],[2,3],resamples=count)
        for seed in (True,-1,2**63,1.5):
            with self.assertRaises(ValueError):paired_interval([1,2],[2,3],seed=seed)

    def test_large_valid_counts_still_obey_total_draw_budget(self):
        with self.assertRaisesRegex(ValueError,"draw budget"):
            paired_interval([0]*10000,[0]*10000,resamples=10000)

    def test_bounded_results_keep_negative_evidence_and_declare_independence_unknown(self):
        result=paired_interval([1,2,3],[3,4,5],resamples=100)
        self.assertEqual(result,paired_interval([1,2,3],[3,4,5],resamples=100))
        self.assertEqual(result["paired_mean_delta"],2)
        self.assertEqual(result["draws"],300)
        self.assertEqual(result["independence"],"CALLER_DECLARED_NOT_VERIFIED")

    def test_nonfinite_inputs_and_overflowing_deltas_are_refused(self):
        for before,after in (([1,float('nan')],[1,2]),([10**1000,1],[1,2]),([-1e308,-1e308],[1e308,1e308])):
            with self.assertRaises(ValueError):paired_interval(before,after,resamples=100)
