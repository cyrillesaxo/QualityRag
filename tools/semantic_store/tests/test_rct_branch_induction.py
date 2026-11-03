"""RCT v1.2 branching grammar tests using the actual SemanticStore."""
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rct_branch_induction import (
    induce_branch_rule, validate_branch_rule, compile_branch_lens)
from rct_lens import persist_lens
from store import SemanticStore


def fixture(prefix: str, *, add_counterexample: bool = False):
    facts = []
    def add(subject, predicate, dest, number):
        facts.append({
            "id": f"{prefix}{number}", "subject": f"{prefix}{subject}",
            "predicate": predicate, "object": f"{prefix}{dest}",
            "source_ref": f"fixture#{number}",
        })
    i = 0
    # All positives include a, b and a distracting c.
    for j in range(3):
        for predicate in ("evidence_a", "evidence_b", "context_c"):
            add(f"case-{j}", predicate, f"answer-{j}", i); i += 1
    # Negative A has a+c, negative B has b+c.
    for predicate in ("evidence_a", "context_c"):
        add("negative-a", predicate, "answer-n", i); i += 1
    for predicate in ("evidence_b", "context_c"):
        add("negative-b", predicate, "answer-n", i); i += 1
    if add_counterexample:
        add("negative-a", "evidence_b", "answer-n", i)
    examples = [
        {"subject": f"{prefix}case-{j}", "object": f"{prefix}answer-{j}",
         "positive": True, "source_ref": f"label#{j}"}
        for j in range(3)
    ] + [
        {"subject":f"{prefix}negative-a","object":f"{prefix}answer-n",
         "positive":False,"source_ref":"label#neg-a"},
        {"subject":f"{prefix}negative-b","object":f"{prefix}answer-n",
         "positive":False,"source_ref":"label#neg-b"},
    ]
    return {"schema":"rct.structured-ast/v1","facts":facts}, examples


class TestBranchInduction(unittest.TestCase):
    def setUp(self):
        self.training,self.labels=fixture("train-")
        self.heldout,self.heldout_labels=fixture("held-")

    def rule(self):
        return induce_branch_rule(self.training,self.labels)

    def test_learns_conjunction_not_single_path(self):
        result=self.rule()
        self.assertEqual(result["status"],"CANDIDATE")
        self.assertEqual(result["operator"],"CONJUNCT_PARALLEL_EDGES")
        self.assertEqual(result["predicate_pair"],["evidence_a","evidence_b"])
        self.assertEqual(result["search_candidate_count"],3)
        self.assertEqual(result["consistent_candidate_count"],1)
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_validates_heldout_negatives(self):
        validation=validate_branch_rule(
            self.training,self.rule(),self.heldout,self.heldout_labels)
        self.assertEqual(validation["status"],"FINITE_GRAPH_MATCH")
        self.assertEqual(validation["finite_graph_verdict"],"SAT")
        self.assertEqual(len(validation["witnesses"]),5)
        self.assertEqual(len(validation["witnesses"][0]["fact_witness"]),2)
        self.assertEqual(validation["witnesses"][-1]["fact_witness"],[])

    def test_new_counterexample_refutes_candidate(self):
        bad,labels=fixture("held-",add_counterexample=True)
        evaluation=validate_branch_rule(self.training,self.rule(),bad,labels)
        self.assertEqual(evaluation["status"],"COUNTEREXAMPLE")
        self.assertEqual(evaluation["finite_graph_verdict"],"UNSAT")
        self.assertEqual(len(evaluation["counterexamples"]),1)
        self.assertEqual(len(evaluation["counterexamples"][0]["fact_witness"]),2)

    def test_ambiguous_conjunction_abstains(self):
        # Removing the negative labels that distinguish candidate pairs causes
        # positive-only supervision to be rejected rather than overfitting.
        with self.assertRaises(ValueError):
            induce_branch_rule(self.training,self.labels[:3])
        # Add a negative with no supporting facts: all pairings now survive.
        unknown=self.labels[:3] + [{
            "subject":"train-unseen","object":"train-unknown",
            "positive":False,"source_ref":"label#unseen"}]
        result=induce_branch_rule(self.training,unknown)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"AMBIGUOUS_BRANCH_RULE")

    def test_bound_exceeded_abstains(self):
        result=induce_branch_rule(self.training,self.labels,max_candidates=2)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"SEARCH_BUDGET_EXCEEDED")

    def test_tampering_rejected_before_evaluation(self):
        rule=self.rule()
        rule["predicate_pair"][0]="fabricated"
        with self.assertRaises(ValueError):
            validate_branch_rule(self.training,rule,self.heldout,self.heldout_labels)

    def test_tampering_rejected_before_persistence(self):
        rule=self.rule()
        validation=validate_branch_rule(self.training,rule,self.heldout,self.heldout_labels)
        rule["predicate_pair"][0]="fabricated"
        with self.assertRaises(ValueError):
            compile_branch_lens(self.heldout,rule=rule,assessment=validation,
                                lens_id="unsafe",purpose="labeled-conjunction")

    def test_store_integration_is_not_semantic_admission(self):
        rule=self.rule()
        assessment=validate_branch_rule(
            self.training,rule,self.heldout,self.heldout_labels)
        lens=compile_branch_lens(self.heldout,rule=rule,assessment=assessment,
                                 lens_id="fork-rule",purpose="labeled-conjunction")
        db=sqlite3.connect(":memory:")
        store=SemanticStore(db)
        store.initialize()
        result=persist_lens(store,lens=lens,source_id="fork",
                            revision="v1",packspec_digest="unverified-packspec")
        self.assertEqual(result["admission"],"INCONCLUSIVE")
        stored=store.object_version("rct:lens:fork-rule","v1")
        self.assertEqual(stored["evaluation"]["finite_graph_verdict"],"SAT")
        self.assertEqual(
            db.execute("SELECT verdict FROM admission_receipts").fetchone()[0],
            "INCONCLUSIVE")

    def test_same_graph_cannot_be_heldout(self):
        with self.assertRaises(ValueError):
            validate_branch_rule(self.training,self.rule(),
                                 self.training,self.labels)

if __name__=="__main__":
    unittest.main()
