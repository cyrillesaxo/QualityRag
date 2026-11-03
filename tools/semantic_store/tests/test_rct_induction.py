"""v1.1 bounded grammar induction: labeled positives, negatives and counterexamples."""
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from rct_induction import induce_rule, validate_rule, compile_induced_lens
from rct_lens import persist_lens
from store import SemanticStore

def make_graph(prefix="", bad=False):
    facts = []
    for i in range(3):
        subject, intermediate, anchor, destination = (
            f"{prefix}object-{i}", f"{prefix}segment-{i}",
            f"{prefix}shape-{i}", f"{prefix}class-{i}")
        for j, (left, verb, right) in enumerate([
            (subject, "part_of", intermediate),
            (intermediate, "maps_to", anchor),
            (anchor, "belongs_to", destination),
        ]):
            facts.append({"id":f"{prefix}f-{i}-{j}", "subject":left,
                         "predicate":verb, "object":right,
                         "source_ref":f"{prefix}manual#{i}-{j}"})
    # Distractors do not supply the derived relation.
    facts.append({"id":f"{prefix}noise","subject":f"{prefix}object-0",
                  "predicate":"visually_near","object":f"{prefix}class-2",
                  "source_ref":"manual#noise"})
    if bad:
        # A counterexample: a negative explicitly labeled object-0/class-2
        # now also has the selected three-hop path.
        facts.extend([
            {"id":f"{prefix}bad-0","subject":f"{prefix}object-0",
             "predicate":"part_of","object":f"{prefix}segment-bad","source_ref":"manual#bad"},
            {"id":f"{prefix}bad-1","subject":f"{prefix}segment-bad",
             "predicate":"maps_to","object":f"{prefix}shape-bad","source_ref":"manual#bad"},
            {"id":f"{prefix}bad-2","subject":f"{prefix}shape-bad",
             "predicate":"belongs_to","object":f"{prefix}class-2","source_ref":"manual#bad"},
        ])
    return {"schema":"rct.structured-ast/v1","facts":facts}

def labels(prefix=""):
    return [
        {"subject":f"{prefix}object-{i}", "object":f"{prefix}class-{i}",
         "positive":True, "source_ref":f"{prefix}expected#{i}"}
        for i in range(3)
    ] + [
        {"subject":f"{prefix}object-0", "object":f"{prefix}class-2",
         "positive":False, "source_ref":f"{prefix}excluded#0"}
    ]

class TestInduction(unittest.TestCase):
    def setUp(self):
        self.train=make_graph("train-")
        self.examples=labels("train-")
        self.valid=make_graph("held-")
        self.valid_examples=labels("held-")

    def test_discovers_three_hop_rule_not_predeclared_predicate_pair(self):
        candidate=induce_rule(self.train,self.examples,max_depth=4)
        self.assertEqual(candidate["status"],"CANDIDATE")
        self.assertEqual(candidate["predicate_sequence"],
                         ["part_of","maps_to","belongs_to"])
        self.assertEqual(candidate["minimum_depth"],3)
        self.assertGreater(candidate["search_work_units"],0)
        self.assertEqual(candidate["qualityrag_admission"],"INCONCLUSIVE")

    def test_evaluates_positive_and_negative_heldout(self):
        rule=induce_rule(self.train,self.examples,max_depth=3)
        result=validate_rule(self.train,rule,self.valid,self.valid_examples)
        self.assertEqual(result["status"],"FINITE_GRAPH_MATCH")
        self.assertEqual(result["finite_graph_verdict"],"SAT")
        self.assertEqual(len(result["witnesses"]),4)
        self.assertEqual(len(result["witnesses"][0]["fact_witness"]),3)
        self.assertEqual(result["witnesses"][-1]["prediction"],
                         "ABSENT_IN_SUPPLIED_GRAPH")

    def test_new_counterexample_is_detected(self):
        rule=induce_rule(self.train,self.examples,max_depth=3)
        bad=make_graph("held-",bad=True)
        result=validate_rule(self.train,rule,bad,self.valid_examples)
        self.assertEqual(result["status"],"COUNTEREXAMPLE")
        self.assertEqual(result["finite_graph_verdict"],"UNSAT")
        self.assertEqual(len(result["counterexamples"]),1)
        self.assertEqual(result["counterexamples"][0]["label"],"NEGATIVE")
        self.assertEqual(len(result["counterexamples"][0]["fact_witness"]),3)

    def test_insufficient_depth_abstains(self):
        candidate=induce_rule(self.train,self.examples,max_depth=2)
        self.assertEqual(candidate["status"],"UNKNOWN")
        self.assertEqual(candidate["reason"],"NO_RULE_SATISFIES_ALL_LABELS")

    def test_ambiguous_minimal_rule_abstains(self):
        graph=make_graph("train-")
        for i in range(3):
            graph["facts"].append({
                "id":f"extra-{i}", "subject":f"train-object-{i}",
                "predicate":"directly_classified_as", "object":f"train-class-{i}",
                "source_ref":"manual#extra"})
        # One-hop rule is uniquely shortest, so not ambiguous yet.
        first=induce_rule(graph,self.examples,max_depth=4)
        self.assertEqual(first["predicate_sequence"],["directly_classified_as"])
        for i in range(3):
            graph["facts"].append({
                "id":f"extra2-{i}", "subject":f"train-object-{i}",
                "predicate":"categorized_as", "object":f"train-class-{i}",
                "source_ref":"manual#extra2"})
        second=induce_rule(graph,self.examples,max_depth=4)
        self.assertEqual(second["status"],"UNKNOWN")
        self.assertEqual(second["reason"],"AMBIGUOUS_MINIMAL_GRAMMAR")

    def test_tampered_proposal_is_rejected(self):
        rule=induce_rule(self.train,self.examples,max_depth=4)
        rule["predicate_sequence"].append("invented")
        with self.assertRaises(ValueError):
            validate_rule(self.train,rule,self.valid,self.valid_examples)

    def test_same_training_validation_rejected(self):
        rule=induce_rule(self.train,self.examples,max_depth=4)
        with self.assertRaises(ValueError):
            validate_rule(self.train,rule,self.train,self.examples)

    def test_explicit_negative_witness_required(self):
        with self.assertRaises(ValueError):
            induce_rule(self.train,[e for e in self.examples if e["positive"]],
                        max_depth=4)

    def test_real_semantic_store_remains_inconclusive(self):
        rule=induce_rule(self.train,self.examples,max_depth=4)
        assessment=validate_rule(self.train,rule,self.valid,self.valid_examples)
        lens=compile_induced_lens(self.valid,rule=rule,assessment=assessment,
                                  lens_id="three-hop",purpose="labeled-graph-lookup")
        db=sqlite3.connect(":memory:")
        store=SemanticStore(db);store.initialize()
        receipt=persist_lens(store,lens=lens,source_id="held-graph",
                             revision="v1",packspec_digest="packspec-unverified")
        self.assertEqual(receipt["admission"],"INCONCLUSIVE")
        self.assertEqual(store.object_version("rct:lens:three-hop","v1")
                         ["evaluation"]["finite_graph_verdict"],"SAT")
        self.assertEqual(db.execute("SELECT verdict FROM admission_receipts").fetchone()[0],
                         "INCONCLUSIVE")

if __name__ == "__main__":
    unittest.main()
