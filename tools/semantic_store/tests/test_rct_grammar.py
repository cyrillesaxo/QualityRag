"""RCT v0.7: typed AST discovery and actual SemanticStore persistence."""
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rct_grammar import discover_grammars, compile_discovered_lens, persist_lens
from store import SemanticStore

BODY = {"schema": "rct.structured-ast/v1", "facts": [
    {"id": "p1", "subject": "head", "predicate": "part_of", "object": "body", "source_ref": "text#1"},
    {"id": "t1", "subject": "head", "predicate": "is_a", "object": "major_region", "source_ref": "text#1"},
    {"id": "p2", "subject": "trunk", "predicate": "part_of", "object": "body", "source_ref": "text#2"},
    {"id": "t2", "subject": "trunk", "predicate": "is_a", "object": "major_region", "source_ref": "text#2"},
    {"id": "p3", "subject": "limbs", "predicate": "part_of", "object": "body", "source_ref": "text#3"},
    {"id": "t3", "subject": "limbs", "predicate": "is_a", "object": "major_region", "source_ref": "text#3"},
    {"id": "d1", "subject": "heart", "predicate": "part_of", "object": "thorax", "source_ref": "text#4"},
    {"id": "d2", "subject": "heart", "predicate": "is_a", "object": "organ", "source_ref": "text#4"},
]}
DRAW = {"schema": "rct.structured-ast/v1", "facts": [
    {"id": "a", "subject": "edge-front", "predicate": "converges_to", "object": "vp-left", "source_ref": "drawing#1"},
    {"id": "b", "subject": "edge-rear", "predicate": "converges_to", "object": "vp-left", "source_ref": "drawing#2"},
    {"id": "c", "subject": "edge-other", "predicate": "converges_to", "object": "vp-right", "source_ref": "drawing#3"},
]}

class TestRCTGrammar(unittest.TestCase):
    def lens(self, src=BODY, lens_id="elementary", kind="typed_parts",
             root="body", member_type="major_region", **kwargs):
        return compile_discovered_lens(src, lens_id=lens_id, purpose="study",
                                       kind=kind, root=root, member_type=member_type,
                                       **kwargs)

    def test_constructs_three_part_abstraction_without_literal_summary(self):
        self.assertNotIn("three", str(BODY).lower())
        result = self.lens()
        group = result["candidate_grammar"]
        self.assertEqual(group["members"], ["head", "limbs", "trunk"])
        self.assertEqual(result["cost_proxy"]["input_fact_count"], 8)
        self.assertEqual(result["cost_proxy"]["active_member_count"], 3)
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")
        self.assertEqual(result["exhaustiveness"], "UNKNOWN")
        self.assertEqual(len(result["candidate_claims"]), 6)

    def test_discovers_multiple_abstractions_without_relabeling(self):
        groups = discover_grammars(BODY)
        self.assertTrue(any(g["root"] == "thorax" and g["members"] == ["heart"] for g in groups))
        self.assertTrue(any(g["root"] == "body" and g["members"] == ["head", "limbs", "trunk"] for g in groups))

    def test_cross_domain_drawing_group(self):
        groups = discover_grammars(DRAW)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["members"], ["edge-front", "edge-rear"])
        self.assertEqual(groups[0]["root"], "vp-left")
        out = self.lens(DRAW, "drawing", "shared_anchor", "vp-left", "converging_edges")
        self.assertEqual(out["local_coverage"], "CANDIDATE_STRUCTURAL_GROUP_FOUND")

    def test_unavailable_grammar_stays_unknown(self):
        r = self.lens(member_type="clinical_anatomy")
        self.assertEqual(r["local_coverage"], "UNKNOWN")
        self.assertEqual(r["candidate_grammar"], None)

    def test_closure_assertion_does_not_authorize(self):
        r = self.lens(closure_claim={"statement": "The listed regions are exhaustive",
                                     "source_ref": "text#teacher",
                                     "reviewer_label": "classroom"})
        self.assertEqual(r["exhaustiveness"], "UNKNOWN")
        self.assertEqual(r["qualityrag_admission"], "INCONCLUSIVE")
        self.assertEqual(r["closure_claim"]["authentication"], "UNVERIFIED_CLOSURE_ASSERTION")

    def test_actual_store_integration_and_tampering(self):
        db = sqlite3.connect(":memory:")
        store = SemanticStore(db)
        store.initialize()
        a = self.lens()
        persisted = persist_lens(store, lens=a, source_id="anatomy",
                                 revision="v1", packspec_digest="packspec-v1")
        self.assertEqual(persisted["admission"], "INCONCLUSIVE")
        self.assertEqual(store.object_version("rct:lens:elementary", "v1")["fingerprint"], a["fingerprint"])
        b = self.lens(lens_id="clinical", root="thorax", member_type="organ")
        persist_lens(store, lens=b, source_id="anatomy",
                     revision="v1", packspec_digest="packspec-v1")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0], 1)
        c = self.lens(lens_id="tampered")
        c["candidate_grammar"]["members"] = ["fabrication"]
        with self.assertRaises(ValueError):
            persist_lens(store, lens=c, source_id="anatomy",
                         revision="v1", packspec_digest="packspec-v1")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM admission_receipts").fetchone()[0], 2)

    def test_duplicate_fact_ids_rejected(self):
        source = {"schema": "rct.structured-ast/v1", "facts": [BODY["facts"][0], BODY["facts"][0]]}
        with self.assertRaises(ValueError):
            discover_grammars(source)

if __name__ == "__main__":
    unittest.main()
