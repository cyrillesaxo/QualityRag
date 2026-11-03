"""Bounded access-control tests for semantic graph traversal."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from query import query_context


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = SemanticStore(self.db)
        self.store.initialize()
        self.store.add_source("doc", "v1", hashlib.sha256(b"source").hexdigest(), {})
        for oid in ("root", "allowed", "secret"):
            self.store.add_object(oid, "v1", "doc", "v1", "CLAIM", {"text": oid})
        self.store.add_edge("edge1", "KNOWLEDGE", "root", "v1", "allowed", "v1",
                            "DEPENDS_ON")
        self.store.add_edge("edge2", "WITNESS", "root", "v1", "secret", "v1",
                            "SUPPORTS", {"sensitive": "never emit"})

    def tearDown(self):
        self.db.close()

    def test_authorization_filters_nodes_and_edges(self):
        def can_read(principal, oid, revision):
            return principal == "viewer" and oid != "secret"
        result = query_context(self.store, principal="viewer", authorize=can_read,
                               object_id="root", revision="v1")
        self.assertEqual({x["object_id"] for x in result["nodes"]},
                         {"root", "allowed"})
        self.assertEqual([x["edge_id"] for x in result["edges"]], ["edge1"])
        self.assertNotIn("secret", str(result))
        self.assertEqual(result["admission"], "INCONCLUSIVE")

    def test_requires_authorizer_and_valid_principal(self):
        with self.assertRaises(PermissionError):
            query_context(self.store, principal="user", authorize=None,
                          object_id="root", revision="v1")
        with self.assertRaises(PermissionError):
            query_context(self.store, principal="", authorize=lambda *args: True,
                          object_id="root", revision="v1")

    def test_root_access_checked_before_existence(self):
        with self.assertRaises(PermissionError):
            query_context(self.store, principal="viewer", authorize=lambda *args: False,
                          object_id="root", revision="v1")

    def test_bounded_result_does_not_leak_unvisited_ids(self):
        result = query_context(self.store, principal="viewer",
                               authorize=lambda *args: True,
                               object_id="root", revision="v1", max_nodes=1)
        self.assertEqual([x["object_id"] for x in result["nodes"]], ["root"])
        self.assertEqual(result["edges"], [])

    def test_finite_hop_and_node_limits(self):
        with self.assertRaises(ValueError):
            query_context(self.store, principal="viewer",
                          authorize=lambda *args: True,
                          object_id="root", revision="v1", max_hops=100)


if __name__ == "__main__":
    unittest.main()
