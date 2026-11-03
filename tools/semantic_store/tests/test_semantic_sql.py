"""SQL-like semantic query console regression and adversarial tests."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from semantic_sql import compile_sql, execute_sql, SemanticSqlError


class SemanticSQLTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = SemanticStore(self.db)
        self.store.initialize()
        self.store.add_source("policy", "r1", hashlib.sha256(b"source").hexdigest(), {})
        for oid in ("root", "visible", "private"):
            self.store.add_object(oid, "r1", "policy", "r1", "CLAIM", {"text":oid})
        self.store.add_edge("knowledge", "KNOWLEDGE", "root", "r1",
                            "visible", "r1", "SUPPORTS")
        self.store.add_edge("secret", "WITNESS", "root", "r1",
                            "private", "r1", "CITES", {"hidden":"secret"})

    def tearDown(self):
        self.db.close()

    def run_sql(self, sql):
        return execute_sql(self.store, sql, principal="viewer",
                           authorize=lambda p, oid, rev: p=="viewer" and oid!="private")

    def test_familiar_select_returns_authorized_context(self):
        r=self.run_sql("SELECT * FROM facts WHERE object_id = 'root' AND revision = 'r1' LIMIT 20;")
        self.assertEqual(r["plan"]["operation"], "BOUNDED_GRAPH_CONTEXT")
        self.assertEqual({n["object_id"] for n in r["result"]["nodes"]}, {"root","visible"})
        self.assertNotIn("private", str(r))
        self.assertNotIn("secret", str(r))
        self.assertFalse(r["can_generate"])
        self.assertEqual(r["admission"], "INCONCLUSIVE")

    def test_explicit_layer_is_typed(self):
        p=compile_sql("select * from FACTS where object_id='root' and revision='r1' and layer='REGIME' limit 2")
        self.assertEqual(p.layers, ("REGIME",))
        self.assertEqual(p.max_nodes, 2)

    def test_query_plan_is_deterministic(self):
        q="SELECT * FROM facts WHERE object_id='root' AND revision='r1'"
        self.assertEqual(compile_sql(q).as_dict(), compile_sql(q).as_dict())

    def test_rejects_sql_injection_and_mutation(self):
        for sql in (
            "DELETE FROM facts",
            "SELECT * FROM facts",
            "SELECT * FROM facts WHERE object_id='root' AND revision='r1'; DROP TABLE facts;",
            "SELECT * FROM facts WHERE object_id='root' OR 1=1 AND revision='r1'",
            "SELECT * FROM sqlite_master WHERE object_id='root' AND revision='r1'",
            "UPDATE facts SET payload='wrong'",
            "SELECT * FROM facts WHERE object_id='root' AND revision='r1' LIMIT 100000",
            "SELECT * FROM facts WHERE object_id='root' AND revision='r1' LIMIT 0",
            "SELECT * FROM facts WHERE object_id='root' AND revision='r1' AND layer='UNKNOWN'",
        ):
            with self.subTest(sql=sql), self.assertRaises(SemanticSqlError):
                compile_sql(sql)

    def test_expand_reuses_bounded_graph_traversal(self):
        r=self.run_sql("SELECT * FROM facts WHERE object_id='root' AND revision='r1' EXPAND 2 LIMIT 20")
        self.assertEqual(r["plan"]["projection"], "EXPAND")
        self.assertEqual(r["plan"]["limits"]["max_hops"], 2)
        self.assertEqual({n["object_id"] for n in r["result"]["nodes"]}, {"root","visible"})

    def test_collapse_is_structural_only_not_semantic_compression(self):
        r=self.run_sql("SELECT * FROM facts WHERE object_id='root' AND revision='r1' COLLAPSE LIMIT 20")
        self.assertEqual(r["result"]["edges"], [])
        self.assertEqual([n["object_id"] for n in r["result"]["nodes"]], ["root"])
        self.assertEqual(r["result"]["projection_warning"],
                         "STRUCTURAL_ROOT_ONLY_NOT_MEANING_PRESERVING")
        self.assertFalse(r["can_generate"])

    def test_governed_by_requires_resolver(self):
        sql="SELECT * FROM facts WHERE object_id='root' AND revision='r1' GOVERNED BY packspec1"
        self.assertEqual(compile_sql(sql).governance_ref, "packspec1")
        with self.assertRaisesRegex(SemanticSqlError, "requires an authenticated"):
            self.run_sql(sql)

    def test_governed_by_is_binding_not_policy_execution(self):
        sql=("SELECT * FROM facts WHERE object_id='root' AND revision='r1' "
             "GOVERNED BY packspec1 EXPAND 1")
        def authorized(principal, ref):
            self.assertEqual((principal,ref),("viewer","packspec1"))
            return {"id":"packspec1","digest":"a"*64,"authorized":True}
        r=execute_sql(self.store,sql,principal="viewer",
                      authorize=lambda p,o,v: p=="viewer" and o!="private",
                      resolve_packspec=authorized)
        self.assertEqual(r["packspec_binding"]["id"],"packspec1")
        self.assertEqual(r["packspec_binding"]["evaluation"],"NOT_PERFORMED")
        self.assertEqual(r["admission"],"INCONCLUSIVE")

    def test_governed_by_rejects_unauthorized_or_unversioned_policy(self):
        sql="SELECT * FROM facts WHERE object_id='root' AND revision='r1' GOVERNED BY packspec1"
        for resolved in (None,{},{"id":"packspec1","authorized":True},
                         {"id":"packspec1","authorized":False,"digest":"a"*64},
                         {"id":"wrong","authorized":True,"digest":"a"*64}):
            with self.subTest(resolved=resolved), self.assertRaises(PermissionError):
                execute_sql(self.store,sql,principal="viewer",
                            authorize=lambda p,o,v:True,
                            resolve_packspec=lambda p,r:resolved)

    def test_rejects_unbounded_expand_and_ambiguous_modes(self):
        for suffix in ("EXPAND 6","EXPAND 999","EXPAND 1 COLLAPSE",
                       "COLLAPSE EXPAND 1","GOVERNED BY bad.policy"):
            with self.subTest(suffix=suffix), self.assertRaises(SemanticSqlError):
                compile_sql("SELECT * FROM facts WHERE object_id='root' AND revision='r1' "+suffix)

    def test_denied_root_fails_before_lookup(self):
        with self.assertRaises(PermissionError):
            execute_sql(self.store, "SELECT * FROM facts WHERE object_id='private' AND revision='r1'",
                        principal="viewer", authorize=lambda p,oid,rev:oid!="private")

    def test_requires_authorization_callback(self):
        with self.assertRaises(PermissionError):
            execute_sql(self.store, "SELECT * FROM facts WHERE object_id='root' AND revision='r1'",
                        principal="viewer", authorize=None)

    def test_sql_quotes_not_interpreted_as_operations(self):
        p=compile_sql("SELECT * FROM facts WHERE object_id='a''b' AND revision='r1'")
        self.assertEqual(p.object_id, "a'b")

    def test_no_automatic_admission_after_empty_result(self):
        result=self.run_sql("SELECT * FROM facts WHERE object_id='missing' AND revision='r1'")
        self.assertEqual(result["result"]["status"], "NOT_FOUND")
        self.assertEqual(result["admission"], "INCONCLUSIVE")

    def test_rejects_empty_identifier_and_oversized_query(self):
        with self.assertRaises(SemanticSqlError):
            compile_sql("SELECT * FROM facts WHERE object_id='' AND revision='r1'")
        with self.assertRaises(SemanticSqlError):
            compile_sql("a"*4097)


if __name__ == "__main__":
    unittest.main()
