"""Bounded RCT grammar synthesis — real SemanticStore integration tests."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import SemanticStore
from rct_lens import persist_lens
from rct_synthesis import propose_compositions, verify_composition, compile_composition_lens

def graph(prefix=""):
    # A and B each have two-hop membership links. No 'derived' relation is provided.
    f=[]
    for i, (member, mid, root) in enumerate([
        ("head","upper","body"),("trunk","center","body"),
        ("front-edge","vp-left","scene"),("rear-edge","vp-right","scene")
    ]):
        f.extend([
            {"id":f"{prefix}a{i}","subject":f"{prefix}{member}",
             "predicate":"projects_to","object":f"{prefix}{mid}","source_ref":f"source#{i}"},
            {"id":f"{prefix}b{i}","subject":f"{prefix}{mid}",
             "predicate":"belongs_to","object":f"{prefix}{root}","source_ref":f"source#{i}"},
        ])
    return {"schema":"rct.structured-ast/v1","facts":f}

class TestRCTGrammarSynthesis(unittest.TestCase):
    def proposal(self):
        src=graph("train-")
        proposals=propose_compositions(src)
        selected=[c for c in proposals if c["predicate_sequence"]==["projects_to","belongs_to"]]
        self.assertEqual(len(selected),1)
        return src,selected[0]

    def test_mines_predicate_pair_not_explicit_output(self):
        src,c=self.proposal()
        self.assertEqual(c["distinct_pairs"],4)
        self.assertTrue(c["output_predicate"].startswith("derived:"))
        self.assertTrue(all(f["predicate"]!="derived" for f in src["facts"]))

    def test_held_out_finite_equivalence(self):
        train,c=self.proposal()
        validation=graph("test-")
        r=verify_composition(train,validation,c)
        self.assertEqual(r["structural_verdict"],"SAT")
        self.assertEqual(r["evaluation_subjects"],len({v for f in validation["facts"] for v in (f["subject"],f["object"])}))
        self.assertEqual(r["validation_pairs"],4)
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(r["trained_on_validation"])

    def test_missing_target_is_not_hallucinated(self):
        train,c=self.proposal()
        validation=graph("test-")
        validation["facts"]=[f for f in validation["facts"] if f["id"]!="test-b0"]
        r=verify_composition(train,validation,c)
        self.assertEqual(r["validation_pairs"],3)
        self.assertFalse(any(e["subject"]=="test-head" for e in r["derived_edges"]))

    def test_tampered_proposal_rejected(self):
        train,c=self.proposal()
        c["predicate_sequence"][1]="fabricated"
        with self.assertRaises(ValueError):
            verify_composition(train,graph("test-"),c)

    def test_unknown_under_insufficient_budget(self):
        train,c=self.proposal()
        r=verify_composition(train,graph("test-"),c,query_budget=1)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")

    def test_no_generic_semantic_transitivity(self):
        train,c=self.proposal()
        # Composition is structural: no transitive or domain meaning is inferred.
        self.assertEqual(c["semantics"],"STRUCTURAL_PATH_ONLY")
        r=verify_composition(train,graph("test-"),c)
        self.assertEqual(r["validation_claim"],"FINITE_GRAPH_REACHABILITY_ONLY")

    def test_real_store_candidate_only(self):
        train,c=self.proposal()
        lens=compile_composition_lens(train,graph("test-"),c,
                                      lens_id="graph-lens",purpose="bounded-two-hop")
        db=sqlite3.connect(":memory:")
        store=SemanticStore(db)
        store.initialize()
        persisted=persist_lens(store,lens=lens,source_id="graph",
                                revision="v1",packspec_digest="packspec-v1")
        self.assertEqual(persisted["admission"],"INCONCLUSIVE")
        stored=store.object_version("rct:lens:graph-lens","v1")
        self.assertEqual(stored["evaluation"]["structural_verdict"],"SAT")
        self.assertEqual(db.execute("SELECT verdict FROM admission_receipts").fetchone()[0],"INCONCLUSIVE")

if __name__=="__main__":
    unittest.main()
