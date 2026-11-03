"""Research-only regression tests for Semantic SQL investigation clauses."""
from pathlib import Path
import hashlib
import sqlite3
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from semantic_sql import SemanticSqlError
from semantic_investigation import compile_investigation,execute_investigation


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        for rev in ("v1","v2"):
            self.store.add_source("manual",rev,hashlib.sha256(rev.encode()).hexdigest(),{})
            self.store.add_object("root",rev,"manual",rev,"CLAIM",
                                  {"text":"Alice pays Bob" if rev=="v1" else "Bob pays Alice"})
            self.store.add_object("witness",rev,"manual",rev,"CLAIM",{"text":"reference"})
            self.store.add_object("private",rev,"manual",rev,"CLAIM",{"text":"SECRET"})
            self.store.add_edge("e-"+rev,"WITNESS","root",rev,"witness",rev,"SUPPORTED_BY")
            self.store.add_edge("s-"+rev,"WITNESS","root",rev,"private",rev,"SECRET_EDGE")
        self.base="SELECT * FROM facts WHERE object_id='root' AND revision='v1'"
        self.authorize=lambda p,oid,rev:p=="analyst" and oid!="private"

    def tearDown(self):
        self.db.close()

    def execute(self,s,**kwargs):
        return execute_investigation(self.store,s,principal="analyst",
                                     authorize=self.authorize,**kwargs)

    def resolver(self,p,ref):
        return {"id":ref,"digest":"b"*64,"authorized":True,
                "required_object_ids":["root","witness","other"]}

    def test_trace_evidence_is_authorized_and_bounded(self):
        r=self.execute(self.base+" TRACE EVIDENCE")
        self.assertEqual(r["plan"]["operation"],"TRACE_EVIDENCE")
        self.assertEqual({x["object_id"] for x in r["result"]["nodes"]},{"root","witness"})
        self.assertEqual([x["layer"] for x in r["result"]["edges"]],["WITNESS"])
        self.assertNotIn("SECRET",str(r))
        self.assertEqual(r["admission"],"INCONCLUSIVE")

    def test_trace_with_expand(self):
        r=self.execute(self.base+" EXPAND 2 TRACE EVIDENCE")
        self.assertEqual(r["plan"]["limits"]["max_hops"],2)

    def test_compare_is_not_semantic_equivalence(self):
        r=self.execute(self.base+" COMPARE WITH 'v2'")
        c=r["comparison"]
        self.assertEqual(c["payload_changed"],["root"])
        self.assertEqual(c["payload_unchanged"],["witness"])
        self.assertEqual(c["scope"],"BOUNDED_AUTHORIZED_STRUCTURAL_DIFF_NOT_SEMANTIC_EQUIVALENCE")
        self.assertNotIn("SECRET",str(r))
        self.assertFalse(r["can_generate"])

    def test_compare_requires_access_to_both_roots(self):
        with self.assertRaises(PermissionError):
            execute_investigation(self.store,self.base+" COMPARE WITH 'v2'",
                                  principal="analyst",
                                  authorize=lambda p,o,r:r=="v1")

    def test_missing_version_does_not_become_deleted_facts(self):
        r=self.execute(self.base+" COMPARE WITH 'v3'")
        self.assertEqual(r["comparison"]["status"],"INCONCLUSIVE_MISSING_VERSION")
        self.assertNotIn("only_in_base",r["comparison"])

    def test_compare_rejects_missing_revision(self):
        with self.assertRaises(SemanticSqlError):
            compile_investigation(self.base+" COMPARE WITH ''")

    def test_gaps_require_versioned_authorized_policy(self):
        s=self.base+" FIND GAPS"
        with self.assertRaises(SemanticSqlError):
            self.execute(s)
        with self.assertRaises(SemanticSqlError):
            self.execute(self.base+" GOVERNED BY packspec1 FIND GAPS")
        with self.assertRaises(PermissionError):
            self.execute(self.base+" GOVERNED BY packspec1 FIND GAPS",
                         resolve_packspec=lambda p,r:{"id":r,"digest":"b"*64,"authorized":False})

    def test_gaps_are_bounded_presence_not_truth(self):
        r=self.execute(self.base+" GOVERNED BY packspec1 FIND GAPS",
                       resolve_packspec=self.resolver)
        self.assertEqual(r["gap_analysis"]["unobserved_ids"],["other"])
        self.assertEqual(r["gap_analysis"]["status"],"BOUNDED_PRESENCE_ONLY")
        self.assertEqual(r["packspec_binding"]["evaluation"],"NOT_PERFORMED")
        self.assertFalse(r["can_generate"])

    def test_gaps_deny_policy_inventory_leak(self):
        def resolver(p,r):
            return {"id":r,"digest":"b"*64,"authorized":True,
                    "required_object_ids":["private"]}
        r=self.execute(self.base+" GOVERNED BY packspec1 FIND GAPS",
                       resolve_packspec=resolver)
        self.assertEqual(r["gap_analysis"]["status"],"INCONCLUSIVE_ACCESS_RESTRICTION")
        self.assertNotIn("private",str(r))
        self.assertNotIn("SECRET",str(r))

    def test_gaps_require_explicit_finite_inventory(self):
        for ids in (None,["root","root"],[""],[{"unhashable":"value"}],list(map(str,range(101)))):
            with self.subTest(ids=ids):
                with self.assertRaises(SemanticSqlError):
                    self.execute(self.base+" GOVERNED BY packspec1 FIND GAPS",
                                 resolve_packspec=lambda p,r:{"id":r,"digest":"b"*64,
                                         "authorized":True,"required_object_ids":ids})

    def test_no_sql_escape_or_arbitrary_operators(self):
        for s in ("TRACE EVIDENCE; DELETE FROM facts",
                  "FIND GAPS COLLAPSE",
                  "COMPARE WITH 'v2' DROP TABLE facts",
                  "TRACE EVIDENCE COMPARE WITH 'v2'",
                  "TRACE EVIDENCE; TRACE EVIDENCE"):
            with self.subTest(s=s), self.assertRaises(SemanticSqlError):
                compile_investigation(self.base+" "+s)

    def test_collapse_rejected_for_investigation(self):
        for s in ("TRACE EVIDENCE","FIND GAPS","COMPARE WITH 'v2'"):
            with self.subTest(s=s),self.assertRaises(SemanticSqlError):
                compile_investigation(self.base+" COLLAPSE "+s)

if __name__=="__main__":
    unittest.main()
