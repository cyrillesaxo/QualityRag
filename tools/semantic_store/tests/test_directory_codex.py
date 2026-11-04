"""Filesystem to immutable Semantic Store to indexed query integration tests."""
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from semantic_codex import CodexError, compile_source
from directory_codex import index_directory, persist_codex, search_store


class DirectoryCodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sub").mkdir()
        (self.root / "team.csv").write_text("name,role\nCyrille,architect\n", encoding="utf8")
        (self.root / "sub" / "notes.json").write_text('{"note":"Cyrille signed"}', encoding="utf8")
        (self.root / "clip.vtt").write_text(
            "WEBVTT\n\n00:00:02.250 --> 00:00:04.000\nCyrille presenting\n", encoding="utf8")
        (self.root / "photo.jpg").write_bytes(b"not indexed: no image adapter")
        self.db = sqlite3.connect(":memory:")
        self.store = SemanticStore(self.db)
        self.store.initialize()
        self.access = lambda user, sid, rev: user == "viewer" and not sid.endswith("notes.json")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def index(self, **kwargs):
        return index_directory(self.store, self.root, namespace="test", principal="viewer",
                               authorize_source=self.access, **kwargs)

    def search(self, **kwargs):
        return search_store(self.store, "Cyrille", namespace="test", principal="viewer",
                            authorize_source=self.access, **kwargs)

    def test_end_to_end_directory_to_store_to_search(self):
        report = self.index()
        self.assertEqual(report["coverage"]["indexed"], 2)
        self.assertEqual(report["coverage"]["denied"], 1)
        self.assertEqual(report["coverage"]["unsupported"], 1)
        hits = self.search()["hits"]
        self.assertEqual({h["format"] for h in hits}, {"csv", "vtt"})
        self.assertEqual(next(h for h in hits if h["format"] == "vtt")["anchor"]["start_ms"], 2250)
        self.assertNotIn("notes.json", str(hits))
        self.assertEqual(self.search()["admission"], "INCONCLUSIVE")
        self.assertEqual(self.search()["visual_identity_recognition"], "NOT_PERFORMED")

    def test_idempotent_index_and_immutable_versions(self):
        self.index()
        second = self.index()
        self.assertEqual(second["coverage"]["unchanged"], 2)
        self.assertEqual(second["coverage"]["indexed"], 0)
        p = self.root / "team.csv"
        p.write_text("name,role\nCyrille,principal architect\n", encoding="utf8")
        third = self.index()
        self.assertEqual(third["coverage"]["indexed"], 1)
        versions = self.db.execute("SELECT revision FROM source_versions WHERE source_id='test/team.csv'").fetchall()
        self.assertEqual(len(versions), 2)
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("DELETE FROM source_versions")

    def test_search_policy_filters_existing_records_even_after_index(self):
        index_directory(self.store, self.root, namespace="test", principal="viewer",
                        authorize_source=lambda *args: True)
        hits = self.search()["hits"]
        self.assertNotIn("notes.json", str(hits))

    def test_source_revision_collision_is_detected(self):
        artifact = compile_source(b'{"note":"Cyrille"}', source_id="test/manual.json",
                                  revision="r1", format="json")
        persist_codex(self.store, artifact)
        same = persist_codex(self.store, artifact)
        self.assertFalse(same["persisted"])
        conflicting = compile_source(b'{"note":"Someone else"}', source_id="test/manual.json",
                                     revision="r1", format="json")
        with self.assertRaises(CodexError):
            persist_codex(self.store, conflicting)

    def test_tampered_artifact_cannot_be_persisted(self):
        artifact = compile_source(b'{"note":"Cyrille"}', source_id="test/manual.json",
                                  revision="r1", format="json")
        artifact["records"][0]["fields"]["note"]["value"] = "modified"
        with self.assertRaises(CodexError):
            persist_codex(self.store, artifact)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0], 0)

    def test_symlink_not_followed(self):
        target = self.root / "outside.json"
        target.write_text('{"note":"Cyrille"}', encoding="utf8")
        link = self.root / "sub" / "outside_link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported")
        report = self.index()
        self.assertEqual(report["coverage"]["symlinks_skipped"], 1)
        self.assertNotIn("outside_link.json", str(self.search()["hits"]))

    def test_strict_limits_and_coverage(self):
        report = self.index(max_files=1)
        self.assertTrue(report["truncated"])
        self.assertEqual(report["coverage"]["files_considered"], 1)
        with self.assertRaises(CodexError):
            self.index(max_files=201)
        with self.assertRaises(CodexError):
            self.search(max_records=5001)
        with self.assertRaises(PermissionError):
            search_store(self.store, "Cyrille", namespace="test", principal="viewer",
                         authorize_source=None)

    def test_no_json_document_semantics_from_filename(self):
        self.index()
        self.assertEqual(
            search_store(self.store, "photo", namespace="test", principal="viewer",
                         authorize_source=self.access)["hits"], [])

    def test_namespace_isolation(self):
        self.index()
        result = search_store(self.store, "Cyrille", namespace="other",
                              principal="viewer", authorize_source=lambda *args: True)
        self.assertEqual(result["hits"], [])


if __name__ == "__main__":
    unittest.main()
