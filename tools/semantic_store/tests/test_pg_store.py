"""Real PostgreSQL RLS tenant-isolation and immutable semantic ledger tests.

Executed against a PostgreSQL 16 service in CI. The normal SQLite workflow
skips when QR_PG_ADMIN_DSN is not configured; never reports PostgreSQL parity
from mock connections.
"""
import os
import sys
import unittest
from pathlib import Path
from uuid import UUID

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pg_store import TenantPostgresStore
from store import digest

ROOT=Path(__file__).resolve().parents[1]
TENANT_A=UUID("11111111-1111-4111-8111-111111111111")
TENANT_B=UUID("22222222-2222-4222-8222-222222222222")


@unittest.skipUnless(os.getenv("QR_PG_ADMIN_DSN"),"Requires real PostgreSQL service")
class PostgresTenantLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg
        cls.admin=psycopg.connect(os.environ["QR_PG_ADMIN_DSN"],autocommit=True)
        migration=(ROOT / "pg" / "001_tenant_ledger.sql").read_text()
        cls.admin.execute(migration)
        for name in ("qr_test_a", "qr_test_b", "qr_test_unbound"):
            cls.admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(name,))
            if not cls.admin.fetchone() if False else False:
                pass
            # The isolated CI PostgreSQL service starts without these roles.
            cls.admin.execute(
                "CREATE ROLE " + name + " LOGIN PASSWORD 'test-only-password'")
            cls.admin.execute("GRANT qr_runtime TO " + name)
        cls.admin.execute("""
            INSERT INTO qr_private.tenant_role_bindings(login_role,tenant_id)
            VALUES ('qr_test_a',%s),('qr_test_b',%s)
        """,(TENANT_A,TENANT_B))
        cls.dsn=dict(host="127.0.0.1",port=5432,dbname="qualityrag",
                     password="test-only-password")
        cls.a=psycopg.connect(user="qr_test_a",autocommit=True,**cls.dsn)
        cls.b=psycopg.connect(user="qr_test_b",autocommit=True,**cls.dsn)
        cls.unbound=psycopg.connect(user="qr_test_unbound",autocommit=True,**cls.dsn)

    @classmethod
    def tearDownClass(cls):
        for conn in (cls.a,cls.b,cls.unbound,cls.admin):
            conn.close()

    def test_role_bound_identity_and_unknown_role_fail_closed(self):
        store_a=TenantPostgresStore(self.a)
        store_b=TenantPostgresStore(self.b)
        self.assertEqual(store_a.tenant_id,TENANT_A)
        self.assertEqual(store_b.tenant_id,TENANT_B)
        with self.assertRaises(PermissionError):
            TenantPostgresStore(self.unbound)

    def test_same_object_id_across_tenants_remains_isolated(self):
        a=TenantPostgresStore(self.a);b=TenantPostgresStore(self.b)
        a.add_source("shared-source","r1","a"*64,{"owner":"tenant-A"})
        b.add_source("shared-source","r1","b"*64,{"owner":"tenant-B"})
        a.add_object("shared-object","v1","shared-source","r1","claim",{"tenant":"A"})
        b.add_object("shared-object","v1","shared-source","r1","claim",{"tenant":"B"})
        self.assertEqual(a.object_version("shared-object","v1"),{"tenant":"A"})
        self.assertEqual(b.object_version("shared-object","v1"),{"tenant":"B"})
        self.assertEqual(
            self.a.execute("SELECT count(*) FROM qr_store.source_versions").fetchone()[0],
            1)
        self.assertEqual(
            self.b.execute("SELECT count(*) FROM qr_store.source_versions").fetchone()[0],
            1)

    def test_cross_tenant_insert_and_sql_identity_override_rejected(self):
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.a.execute("""
                INSERT INTO qr_store.source_versions
                  (tenant_id,source_id,revision,source_sha256,metadata_json)
                VALUES (%s,'cross-tenant','v1',%s,'{}'::jsonb)
            """,(TENANT_B,"a"*64))
        self.a.execute("SET app.tenant_id = %s",(str(TENANT_B),))
        self.assertEqual(self.a.execute(
            "SELECT qr_private.authenticated_tenant()").fetchone()[0],TENANT_A)
        self.assertEqual(self.a.execute(
            "SELECT count(*) FROM qr_store.source_versions WHERE tenant_id=%s",
            (TENANT_B,)).fetchone()[0],0)

    def test_admission_cannot_be_fabricated_even_with_direct_sql(self):
        a=TenantPostgresStore(self.a)
        if a.object_version("shared-object","v1") is None:
            a.add_source("s-admit","r1","a"*64,{})
            a.add_object("o-admit","v1","s-admit","r1","claim",{})
            target="o-admit"
        else:
            target="shared-object"
        receipt=a.record_admission(target,"v1","pack",[{"status":"SAT"}])
        self.assertEqual(receipt.status,"INCONCLUSIVE")
        self.assertEqual(a.record_admission(
            target,"v1","pack",[{"status":"FAIL"}]).status,"REFUSE")
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            self.a.execute("""
                INSERT INTO qr_store.admission_receipts
                  (tenant_id,receipt_hash,object_id,revision,packspec_digest,
                   verdict,reason,checks_json)
                VALUES (qr_private.authenticated_tenant(),%s,%s,'v1',
                        'pack','ADMIT','fake','[]'::jsonb)
            """,("a"*64,target))

    def test_immutable_rows_and_unprivileged_roles(self):
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.a.execute("UPDATE qr_store.source_versions SET revision='tampered'")
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.a.execute("DELETE FROM qr_store.source_versions")
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.a.execute("SELECT * FROM qr_private.tenant_role_bindings")
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.a.execute("TRUNCATE qr_store.source_versions")
        with self.assertRaises(Exception):
            self.a.execute("SET ROLE qr_test_b")

    def test_direct_admin_update_is_stopped_by_immutable_trigger(self):
        with self.assertRaises(self.psycopg.errors.RaiseException):
            self.admin.execute("DELETE FROM qr_store.source_versions")

    def test_cross_tenant_edges_fail_foreign_keys(self):
        a=TenantPostgresStore(self.a)
        b=TenantPostgresStore(self.b)
        a.add_source("edge-a","r1","a"*64,{})
        b.add_source("edge-b","r1","b"*64,{})
        a.add_object("edge-A","v1","edge-a","r1","claim",{})
        b.add_object("edge-B","v1","edge-b","r1","claim",{})
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            a.add_edge("wrong","WITNESS","edge-A","v1","edge-B","v1","related")
        a.add_edge("okay","WITNESS","edge-A","v1","edge-A","v1","self")
        self.assertEqual(self.a.execute(
            "SELECT count(*) FROM qr_store.semantic_edges").fetchone()[0],1)
        self.assertEqual(self.b.execute(
            "SELECT count(*) FROM qr_store.semantic_edges").fetchone()[0],0)


if __name__=="__main__":
    unittest.main()
