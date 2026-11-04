"""Public SQL-like FIND -> indexed Semantic Store integration tests."""
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from directory_codex import index_directory
from semantic_find_sql import compile_find,execute_find
from semantic_codex import CodexError

class DirectoryFindTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        (Path(self.directory.name)/"team.csv").write_text("name\nCyrille\n",encoding="utf-8")
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        self.authorize=lambda p,s,r:p=="owner" and s.startswith("work/")
        index_directory(self.store,self.directory.name,namespace="work",
                        principal="owner",authorize_source=self.authorize)

    def tearDown(self):
        self.db.close()
        self.directory.cleanup()

    def test_compiles_and_executes_familiar_find(self):
        sql="FIND 'Cyrille' IN 'work' LIMIT 10;"
        plan=compile_find(sql)
        self.assertEqual(plan.as_dict()["operation"],"INDEXED_LEXICAL_FIND")
        result=execute_find(self.store,sql,principal="owner",
                            authorize_source=self.authorize)
        self.assertEqual(len(result["result"]["hits"]),1)
        self.assertEqual(result["result"]["hits"][0]["anchor"]["row_number"],2)
        self.assertFalse(result["can_generate"])

    def test_source_authorization_is_enforced_at_query(self):
        result=execute_find(self.store,"FIND 'Cyrille' IN 'work'",
                            principal="outsider",authorize_source=self.authorize)
        self.assertEqual(result["result"]["hits"],[])

    def test_no_arbitrary_sql_execution(self):
        for sql in ("FIND 'Cyrille' IN 'work'; DELETE FROM source_versions;",
                    "SELECT * FROM source_versions",
                    "FIND 'Cyrille' IN '../secret'",
                    "FIND '' IN 'work'",
                    "FIND 'Cyrille' IN 'work' LIMIT 0",
                    "FIND 'Cyrille' IN 'work' LIMIT 101"):
            with self.subTest(sql=sql),self.assertRaises(CodexError):
                compile_find(sql)

    def test_sql_literal_escaping(self):
        plan=compile_find("FIND 'Cyrille''s notes' IN 'work'")
        self.assertEqual(plan.term,"Cyrille's notes")

if __name__=="__main__":
    unittest.main()
