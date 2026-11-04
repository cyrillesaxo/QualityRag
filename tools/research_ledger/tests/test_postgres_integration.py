"""Live PostgreSQL integration checks; run against disposable test database only.

Environment: QUALITYRAG_TEST_DATABASE_URL. CI creates temporary PostgreSQL 16
service and runs the real schema, writes, migration, and refusal semantics.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ledger
import postgres
from migrate_sqlite_to_postgres import import_sqlite


@unittest.skipUnless(os.environ.get("QUALITYRAG_TEST_DATABASE_URL"),"Real PostgreSQL test DSN not set")
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn=os.environ["QUALITYRAG_TEST_DATABASE_URL"]
        cls.conn=postgres.connect(cls.dsn)
        schema=Path(__file__).resolve().parents[1]/"postgresql.sql"
        cls.conn.execute(schema.read_text("utf-8"))
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        # Every individual test uses a fresh set of globally unique IDs.
        self.tag=self.id().rsplit(".",1)[-1]

    def test_postgresql_write_and_evidence_gate(self):
        c="pg.test."+self.tag
        e="pg.code."+self.tag
        t="pg.tests."+self.tag
        postgres.claim(self.conn,claim_id=c,project="QualityRag",
                       kind="HYPOTHESIS",statement="Postgres adapter is correct")
        postgres.evidence(self.conn,evidence_id=e,kind="CODE_COMMIT",
                          uri="https://example.org/commit",description="Test evidence")
        postgres.evidence(self.conn,evidence_id=t,kind="TEST_RESULT",
                          uri="https://example.org/ci",description="Test CI")
        postgres.assess(self.conn,event_id="pg.implemented."+self.tag,claim_id=c,
                        assessment="IMPLEMENTED",reason="Code available",
                        actor="ci",evidence_ids=[e])
        postgres.assess(self.conn,event_id="pg.tested."+self.tag,claim_id=c,
                        assessment="TESTED",reason="CI ran",actor="ci",evidence_ids=[t])
        report=postgres.progress(self.conn,project="QualityRag")
        item=next(x for x in report["claims"] if x["claim_id"]==c)
        self.assertEqual(item["status"],"TESTED")
        self.assertEqual(len(item["events"]),2)
        with self.assertRaises(ledger.LedgerError):
            postgres.assess(self.conn,event_id="pg.validated."+self.tag,claim_id=c,
                            assessment="VALIDATED",reason="Cannot claim proof",
                            actor="ci",evidence_ids=[e,t])
        with self.assertRaises(Exception):
            with self.conn.transaction():
                self.conn.execute("UPDATE research.claims SET statement='tamper' WHERE claim_id=%s",(c,))
        self.conn.rollback()

    def test_migration_preserves_original_hashes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"research.sqlite3"
            db=sqlite3.connect(path)
            ledger.initialize(db)
            cid="pg.migration."+self.tag
            evid="pg.migration.evidence."+self.tag
            ledger.claim(db,claim_id=cid,project="QualityRag",
                         kind="EXPERIMENT",statement="Portable research migration")
            ledger.evidence(db,evidence_id=evid,kind="SOURCE_DOCUMENT",
                            uri="https://example.org/source",description="Source of migration")
            ledger.assess(db,event_id="pg.migrated."+self.tag,claim_id=cid,
                          assessment="INCONCLUSIVE",reason="No independent validation",
                          actor="ci",evidence_ids=[evid])
            db.close()
            dry=import_sqlite(path,self.conn,dry_run=True)
            self.assertEqual(dry["would_import_rows"],3)
            self.assertEqual(dry["new_rows"],0)
            a=import_sqlite(path,self.conn)
            self.assertEqual(a["new_rows"],3)
            b=import_sqlite(path,self.conn)
            self.assertEqual(b["new_rows"],0)
            original=sqlite3.connect(path)
            original_event=original.execute(
                "SELECT event_hash FROM research_events").fetchone()[0]
            original.close()
            target_event=self.conn.execute(
                "SELECT event_hash FROM research.assessment_events WHERE claim_id=%s",(cid,)).fetchone()[0]
            self.assertEqual(original_event,target_event)

    def test_conflict_rejected_without_overwrite(self):
        cid="pg.conflict."+self.tag
        postgres.claim(self.conn,claim_id=cid,project="QualityRag",
                       kind="CAPABILITY",statement="Existing cloud statement")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"conflict.sqlite3"
            db=sqlite3.connect(path)
            ledger.initialize(db)
            ledger.claim(db,claim_id=cid,project="QualityRag",
                         kind="CAPABILITY",statement="Different local statement")
            db.close()
            with self.assertRaises(ledger.LedgerError):
                import_sqlite(path,self.conn)
            self.conn.rollback()
            row=self.conn.execute("SELECT statement FROM research.claims WHERE claim_id=%s",(cid,)).fetchone()
            self.assertEqual(row[0],"Existing cloud statement")

if __name__=="__main__":
    unittest.main()
