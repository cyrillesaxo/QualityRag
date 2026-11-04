"""Real PostgreSQL only: no mocked transaction or replay-store behavior."""
import os
from pathlib import Path
import unittest
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import review_binding
from tools.activation_runtime.postgres_validation import postgres,review_context,validate_claim
from tools.activation_runtime.gardener import ledger

AT="2026-11-04T12:00:00Z"


@unittest.skipUnless(os.environ.get("QUALITYRAG_TEST_DATABASE_URL"),"Real PostgreSQL test DSN not set")
class PostgresValidationTests(unittest.TestCase):
    def setUp(self):
        self.conn=postgres.connect(os.environ["QUALITYRAG_TEST_DATABASE_URL"])
        self.addCleanup(self.conn.close)
        schema=Path(__file__).resolve().parents[2]/"research_ledger"/"postgresql.sql"
        self.conn.execute(schema.read_text());self.conn.commit();self.conn.autocommit=True
        self.tag=uuid4().hex
        self.cid="claim."+self.tag;self.rid="review."+self.tag;self.tid="test."+self.tag
        self.event="event."+self.tag
        self.author=Ed25519PrivateKey.generate();self.reviewer=Ed25519PrivateKey.generate()
        postgres.claim(self.conn,claim_id=self.cid,project="fixture",kind="EXPERIMENT",statement="Authored cryptographic fixture only",at=AT)
        for eid,kind in ((self.rid,"REVIEW"),(self.tid,"TEST_RESULT")):
            postgres.evidence(self.conn,evidence_id=eid,kind=kind,uri="https://example.invalid/fixture",description="Authored test evidence",at=AT)

    def context(self,**changes):
        claim=self.conn.execute("SELECT claim_id,content_hash FROM research.claims WHERE claim_id=%s",(self.cid,)).fetchone()
        evidence=self.conn.execute("SELECT evidence_id,record_hash FROM research.evidence WHERE evidence_id=ANY(%s)",([self.rid,self.tid],)).fetchall()
        args=dict(claim={"claim_id":claim[0],"content_hash":claim[1]},
                  evidence=[{"evidence_id":r[0],"record_hash":r[1]} for r in evidence],
                  scope="AUTHORED_FIXTURE_ONLY",tenant="fixture",ledger_id="test-ledger",
                  actor="reviewer",event_id=self.event)
        args.update(changes)
        return review_context(self.conn,**args)

    def signed(self,*,nonce=None,context=None,key=None):
        return review_binding(context or self.context(),decision="APPROVE",reviewer="reviewer",
            author_key_id="author",key=key or self.reviewer,key_id="reviewer",
            issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce=nonce or self.tag)

    def validate(self,envelope=None,**changes):
        args=dict(event_id=self.event,claim_id=self.cid,actor="reviewer",evidence_ids=[self.rid,self.tid],
                  scope="AUTHORED_FIXTURE_ONLY",signed_review=envelope or self.signed(),
                  reviewer_keys={"reviewer":self.reviewer.public_key()},author_public_key=self.author.public_key(),
                  as_of=AT,tenant="fixture",ledger_id="test-ledger")
        args.update(changes)
        return validate_claim(self.conn,**args)

    def receipts(self):
        return self.conn.execute("SELECT count(*) FROM research.validation_receipts WHERE event_id=%s",(self.event,)).fetchone()[0]

    def test_signed_validation_persists_exact_review_and_immutable_receipt(self):
        envelope=self.signed();result=self.validate(envelope)
        self.assertEqual(result["assessment"],"VALIDATED")
        row=self.conn.execute("SELECT reviewer,review_envelope FROM research.validation_receipts WHERE event_id=%s",(self.event,)).fetchone()
        self.assertEqual(row,("reviewer",envelope))
        item=next(c for c in postgres.progress(self.conn,"fixture")["claims"] if c["claim_id"]==self.cid)
        self.assertEqual(item["status"],"VALIDATED")
        self.assertTrue(postgres.verify_integrity(self.conn)["consistent"])
        for operation in ("UPDATE research.validation_receipts SET reviewer='changed' WHERE event_id=%s",
                          "DELETE FROM research.validation_receipts WHERE event_id=%s"):
            with self.assertRaises(Exception):self.conn.execute(operation,(self.event,))

    def test_scope_tenant_ledger_actor_signature_and_expiry_fail_without_consuming_nonce(self):
        envelope=self.signed()
        for changes in ({"scope":"DIFFERENT"},{"tenant":"other"},{"ledger_id":"other"},
                        {"actor":"other"},{"as_of":"2026-11-06T00:00:00Z"},
                        {"reviewer_keys":{"reviewer":self.author.public_key()}},
                        {"author_public_key":self.reviewer.public_key()}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ledger.LedgerError):self.validate(envelope,**changes)
                self.assertEqual(self.receipts(),0)
        self.validate(envelope)

    def test_reviewer_cannot_impersonate_event_actor(self):
        envelope=self.signed(context=self.context(actor="other"))
        with self.assertRaises(ledger.LedgerError):self.validate(envelope,actor="other")
        self.assertEqual(self.receipts(),0)

    def test_replay_fails_for_second_event_and_keeps_original(self):
        self.validate()
        event=self.event+".second"
        envelope=self.signed(context=self.context(event_id=event))
        with self.assertRaises(ledger.LedgerError):self.validate(envelope,event_id=event,as_of="2026-11-04T12:00:01Z")
        self.assertEqual(self.receipts(),1)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM research.assessment_events WHERE event_id=%s",(event,)).fetchone())

    def test_concurrent_workers_cannot_consume_one_nonce_twice(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        other=self.cid+".other"
        postgres.claim(self.conn,claim_id=other,project="fixture",kind="EXPERIMENT",statement="Second concurrent fixture",at=AT)
        row=self.conn.execute("SELECT content_hash FROM research.claims WHERE claim_id=%s",(other,)).fetchone()
        events=[self.event,self.event+".other"]
        reviews=[self.signed(),self.signed(context=self.context(
            claim={"claim_id":other,"content_hash":row[0]},event_id=events[1]))]
        barrier=Barrier(2)
        def worker(index):
            conn=postgres.connect(os.environ["QUALITYRAG_TEST_DATABASE_URL"])
            conn.autocommit=True
            try:
                barrier.wait(timeout=10)
                try:
                    validate_claim(conn,event_id=events[index],claim_id=[self.cid,other][index],actor="reviewer",
                        evidence_ids=[self.rid,self.tid],scope="AUTHORED_FIXTURE_ONLY",signed_review=reviews[index],
                        reviewer_keys={"reviewer":self.reviewer.public_key()},author_public_key=self.author.public_key(),
                        as_of=AT,tenant="fixture",ledger_id="test-ledger")
                    return True
                except ledger.LedgerError:return False
            finally:conn.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(worker,range(2)))
        self.assertEqual(sorted(outcomes),[False,True])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM research.validation_receipts WHERE tenant='fixture' AND nonce=%s",(self.tag,)).fetchone()[0],1)

    def test_missing_review_or_host_verifier_never_validates(self):
        for evidence_ids in ([],[self.tid]):
            with self.assertRaises(ledger.LedgerError):self.validate(evidence_ids=evidence_ids)
        with self.assertRaises(ledger.LedgerError):
            postgres.assess(self.conn,event_id=self.event,claim_id=self.cid,assessment="VALIDATED",
                reason="Boolean cannot authorize validation",actor="reviewer",evidence_ids=[self.rid,self.tid],verify_validation=True,at=AT)
        self.assertEqual(self.receipts(),0)

    def test_tampered_record_hash_refuses_and_rolls_back(self):
        # A privileged writer can insert a malformed row; validation must detect it.
        with self.assertRaises(ledger.LedgerError):
            with self.conn.transaction():
                self.conn.execute("INSERT INTO research.evidence VALUES (%s,'REVIEW','https://example.invalid/corrupt','Corrupt fixture',NULL,%s,'{}',%s)",
                                  ("corrupt."+self.tag,AT,"0"*64))
                self.validate()
        self.assertEqual(self.receipts(),0)
        self.assertTrue(postgres.verify_integrity(self.conn)["consistent"])

    def test_event_failure_rolls_back_nonce_then_same_signed_review_succeeds(self):
        from psycopg import sql
        name="fail_"+self.tag
        self.conn.execute(sql.SQL("CREATE FUNCTION research.{}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected write failure'; END $$").format(sql.Identifier(name)))
        self.conn.execute(sql.SQL("CREATE TRIGGER {} BEFORE INSERT ON research.assessment_events FOR EACH ROW EXECUTE FUNCTION research.{}()").format(sql.Identifier(name),sql.Identifier(name)))
        envelope=self.signed()
        try:
            with self.assertRaises(Exception):self.validate(envelope)
            self.assertEqual(self.receipts(),0)
        finally:
            self.conn.execute(sql.SQL("DROP TRIGGER {} ON research.assessment_events").format(sql.Identifier(name)))
            self.conn.execute(sql.SQL("DROP FUNCTION research.{}()").format(sql.Identifier(name)))
        self.validate(envelope)
        self.assertEqual(self.receipts(),1)

    def test_backdated_assessment_cannot_break_existing_chain(self):
        self.validate()
        with self.assertRaisesRegex(ledger.LedgerError,"event-chain head"):
            postgres.assess(self.conn,event_id=self.event+".earlier",claim_id=self.cid,
                assessment="INCONCLUSIVE",reason="Backdated fixture",actor="reviewer",evidence_ids=[],at="2026-11-03T12:00:00Z")
        self.assertTrue(postgres.verify_integrity(self.conn)["consistent"])

    def test_intervening_assessment_invalidates_stale_review(self):
        envelope=self.signed()
        postgres.assess(self.conn,event_id=self.event+".before",claim_id=self.cid,
            assessment="INCONCLUSIVE",reason="New evidence requires renewed review",actor="reviewer",
            evidence_ids=[],at="2026-11-04T11:59:59Z")
        with self.assertRaises(ledger.LedgerError):self.validate(envelope)
        self.assertEqual(self.receipts(),0)

    def test_migration_cannot_launder_validation_without_destination_review(self):
        import sqlite3
        import tempfile
        from migrate_sqlite_to_postgres import import_sqlite
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"source.sqlite"
            db=sqlite3.connect(path)
            try:
                ledger.initialize(db)
                ledger.claim(db,claim_id="migrated."+self.tag,project="fixture",kind="EXPERIMENT",statement="Source-only validation",at=AT)
                for eid,kind in (("r","REVIEW"),("t","TEST_RESULT")):
                    ledger.evidence(db,evidence_id=eid,kind=kind,uri="https://example.invalid/source",description="Source fixture",at=AT)
                ledger.assess(db,event_id="v",claim_id="migrated."+self.tag,assessment="VALIDATED",
                    reason="Source host approval does not authorize the destination",actor="source",evidence_ids=["r","t"],at=AT,
                    verify_validation=lambda claim,evidence:True)
            finally:db.close()
            with self.assertRaisesRegex(ledger.LedgerError,"destination-bound"):
                import_sqlite(path,self.conn)
            self.assertIsNone(self.conn.execute("SELECT 1 FROM research.claims WHERE claim_id=%s",("migrated."+self.tag,)).fetchone())
