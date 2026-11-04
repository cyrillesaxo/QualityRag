"""Actual durable SQLite transactions and signatures; no mocked replay store."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import review_binding
from tools.activation_runtime.gardener import ledger
from tools.activation_runtime.ledger_validation import review_context,validate_claim

AT="2026-11-04T12:00:00Z"


class SQLiteValidationAtomicTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"ledger.sqlite"
        self.db=sqlite3.connect(self.path,timeout=10);self.addCleanup(self.db.close)
        ledger.initialize(self.db)
        for cid in ("claim-one","claim-two"):
            ledger.claim(self.db,claim_id=cid,project="fixture",kind="EXPERIMENT",statement="Authored fixture only",at=AT)
        for eid,kind in (("review","REVIEW"),("test","TEST_RESULT")):
            ledger.evidence(self.db,evidence_id=eid,kind=kind,uri="https://example.invalid/fixture",description="Authored evidence fixture",at=AT)
        self.author=Ed25519PrivateKey.generate();self.reviewer=Ed25519PrivateKey.generate()

    def context(self,*,cid="claim-one",event="event-one",**changes):
        claim=self.db.execute("SELECT content_hash FROM research_claims WHERE claim_id=?",(cid,)).fetchone()
        rows=self.db.execute("SELECT evidence_id,record_hash FROM research_evidence").fetchall()
        args=dict(claim={"claim_id":cid,"content_hash":claim[0]},
            evidence=[{"evidence_id":r[0],"record_hash":r[1]} for r in rows],scope="FIXTURE_ONLY",
            tenant="fixture",ledger_id="ledger-one",actor="reviewer",event_id=event)
        args.update(changes)
        return review_context(self.db,**args)

    def signed(self,context=None,nonce="one"):
        return review_binding(context or self.context(),decision="APPROVE",reviewer="reviewer",author_key_id="author",
            key=self.reviewer,key_id="reviewer",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce=nonce)

    def validate(self,envelope=None,db=None,**changes):
        args=dict(event_id="event-one",claim_id="claim-one",actor="reviewer",evidence_ids=["review","test"],
            scope="FIXTURE_ONLY",signed_review=envelope or self.signed(),reviewer_keys={"reviewer":self.reviewer.public_key()},
            author_public_key=self.author.public_key(),as_of=AT,tenant="fixture",ledger_id="ledger-one")
        args.update(changes)
        return validate_claim(db or self.db,**args)

    def count(self):
        return self.db.execute("SELECT count(*) FROM research_validation_receipts").fetchone()[0]

    def test_event_failure_does_not_consume_approval(self):
        envelope=self.signed()
        self.db.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON research_events BEGIN SELECT RAISE(ABORT,'fixture write failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.validate(envelope)
        self.assertEqual(self.count(),0)
        self.db.execute("DROP TRIGGER injected_failure")
        self.validate(envelope)
        self.assertEqual(self.count(),1)
        stored=self.db.execute("SELECT review_envelope FROM research_validation_receipts").fetchone()[0]
        self.assertEqual(json.loads(stored),envelope)

    def test_caller_rollback_removes_event_and_receipt_together(self):
        envelope=self.signed()
        self.db.execute("BEGIN IMMEDIATE")
        self.validate(envelope)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.count(),1)
        self.db.rollback()
        self.assertEqual(self.count(),0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_events").fetchone()[0],0)
        self.validate(envelope)

    def test_wrong_scope_tenant_ledger_actor_key_and_expiry_leave_nonce_unused(self):
        envelope=self.signed()
        for changes in ({"scope":"OTHER"},{"tenant":"other"},{"ledger_id":"other"},{"actor":"other"},
            {"reviewer_keys":{"reviewer":self.author.public_key()}},{"author_public_key":self.reviewer.public_key()},
            {"as_of":"2026-11-06T00:00:00Z"}):
            with self.subTest(fields=list(changes)):
                with self.assertRaises(ledger.LedgerError):self.validate(envelope,**changes)
                self.assertEqual(self.count(),0)
        self.validate(envelope)

    def test_signer_cannot_impersonate_event_actor(self):
        signed=self.signed(self.context(actor="other"))
        with self.assertRaises(ledger.LedgerError):self.validate(signed,actor="other")
        self.assertEqual(self.count(),0)

    def test_intervening_event_requires_new_review(self):
        envelope=self.signed()
        ledger.assess(self.db,event_id="earlier",claim_id="claim-one",assessment="INCONCLUSIVE",
            reason="Changed claim state",actor="reviewer",evidence_ids=[],at="2026-11-04T11:59:59Z")
        with self.assertRaises(ledger.LedgerError):self.validate(envelope)
        self.assertEqual(self.count(),0)
        self.validate(self.signed())

    def test_replay_is_refused_even_with_new_signed_event_context(self):
        self.validate()
        signed=self.signed(self.context(cid="claim-two",event="event-two"))
        with self.assertRaises(ledger.LedgerError):self.validate(signed,claim_id="claim-two",event_id="event-two")
        self.assertEqual(self.count(),1)

    def test_two_connections_cannot_consume_same_nonce(self):
        envelopes=[self.signed(),self.signed(self.context(cid="claim-two",event="event-two"))]
        barrier=Barrier(2)
        def worker(index):
            db=sqlite3.connect(self.path,timeout=10)
            db.execute("PRAGMA foreign_keys=ON")
            try:
                barrier.wait(timeout=10)
                try:
                    self.validate(envelopes[index],db=db,claim_id=["claim-one","claim-two"][index],event_id=["event-one","event-two"][index])
                    return True
                except ledger.LedgerError:return False
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(self.count(),1)
        self.assertTrue(ledger.verify_integrity(self.db)["consistent"])

    def test_backdated_append_and_receipt_mutation_are_refused(self):
        self.validate()
        with self.assertRaisesRegex(ledger.LedgerError,"event-chain head"):
            ledger.assess(self.db,event_id="earlier",claim_id="claim-one",assessment="INCONCLUSIVE",
                reason="Backdated fixture",actor="reviewer",evidence_ids=[],at="2026-11-03T12:00:00Z")
        for sql in ("DELETE FROM research_validation_receipts","UPDATE research_validation_receipts SET reviewer='other'"):
            with self.assertRaises(sqlite3.IntegrityError):self.db.execute(sql)
            self.db.rollback()
        self.assertEqual(self.count(),1)

    def test_in_memory_validation_refuses_durability_claim(self):
        db=sqlite3.connect(":memory:")
        try:
            ledger.initialize(db)
            with self.assertRaisesRegex(ValueError,"Durable SQLite"):self.validate(self.signed(),db=db)
        finally:db.close()

    def test_changed_dependency_graph_invalidates_old_signed_context(self):
        envelope=self.signed()
        # Authorize the parent with an independent authored signature first.
        parent=self.signed(self.context(cid="claim-two",event="parent-validation"),nonce="parent")
        self.validate(parent,claim_id="claim-two",event_id="parent-validation")
        ledger.link(self.db,link_id="dependency",from_claim="claim-one",to_claim="claim-two",relation="DEPENDS_ON",at=AT)
        with self.assertRaises(ledger.LedgerError):self.validate(envelope)
        self.assertEqual(self.count(),1)
        self.validate(self.signed())
