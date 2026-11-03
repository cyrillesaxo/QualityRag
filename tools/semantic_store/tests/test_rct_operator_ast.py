"""Integration tests for compositional RCT grammar AST v1.3."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_operator_ast import (
    induce_operator_ast, validate_operator_ast, compile_operator_lens)
from rct_lens import persist_lens
from store import SemanticStore


def fixture(prefix, *, contradiction=False):
    facts, examples = [], []
    def edge(s, pred, o):
        facts.append({
            "id": f"{prefix}edge-{len(facts)}",
            "subject": f"{prefix}{s}", "predicate": pred,
            "object": f"{prefix}{o}", "source_ref": "auth-unverified#fixture"})
    for i in range(3):
        edge(f"case{i}", "p", f"intermediate{i}")
        edge(f"intermediate{i}", "q", f"answer{i}")
        edge(f"case{i}", "r", f"answer{i}")
        examples.append({
            "subject": f"{prefix}case{i}", "object": f"{prefix}answer{i}",
            "positive": True, "source_ref": f"label#{i}"})
    # Negative 1 has the whole p/q PATH but lacks direct r guard.
    edge("negative-path", "p", "intermediate-n")
    edge("intermediate-n", "q", "answer-n")
    examples.append({"subject": f"{prefix}negative-path",
                     "object": f"{prefix}answer-n", "positive": False,
                     "source_ref": "label#negative-path"})
    # Negative 2 has r guard but lacks p/q path.
    edge("negative-guard", "r", "answer-g")
    examples.append({"subject": f"{prefix}negative-guard",
                     "object": f"{prefix}answer-g", "positive": False,
                     "source_ref": "label#negative-guard"})
    if contradiction:
        edge("negative-path", "r", "answer-n")
    return {"schema": "rct.structured-ast/v1", "facts": facts}, examples


class TestOperatorAST(unittest.TestCase):
    def setUp(self):
        self.train, self.train_labels = fixture("train-")
        self.held, self.held_labels = fixture("held-")

    def rule(self):
        return induce_operator_ast(self.train, self.train_labels)

    def test_mixed_path_and_guard_required(self):
        rule = self.rule()
        self.assertEqual(rule["status"], "CANDIDATE")
        self.assertEqual(rule["ast"], {
            "op": "AND",
            "left": {"op": "PATH",
                     "left": {"op": "EDGE", "predicate": "p"},
                     "right": {"op": "EDGE", "predicate": "q"}},
            "right": {"op": "EDGE", "predicate": "r"},
        })
        self.assertEqual(rule["ast_nodes"], 5)
        self.assertEqual(rule["qualityrag_admission"], "INCONCLUSIVE")

    def test_heldout_negative_witnesses_and_positive_provenance(self):
        rule = self.rule()
        result = validate_operator_ast(
            self.train, rule, self.held, self.held_labels)
        self.assertEqual(result["status"], "FINITE_GRAPH_MATCH")
        self.assertEqual(result["finite_graph_verdict"], "SAT")
        self.assertEqual(len(result["witnesses"]), 5)
        self.assertEqual(len(result["witnesses"][0]["fact_witness"]), 3)
        self.assertFalse(result["witnesses"][-1]["fact_witness"])

    def test_adversarial_added_edge_refutes(self):
        rule = self.rule()
        bad, labels = fixture("held-", contradiction=True)
        result = validate_operator_ast(self.train, rule, bad, labels)
        self.assertEqual(result["status"], "COUNTEREXAMPLE")
        self.assertEqual(result["finite_graph_verdict"], "UNSAT")
        self.assertEqual(len(result["counterexamples"]), 1)
        self.assertEqual(len(result["counterexamples"][0]["fact_witness"]), 3)

    def test_candidate_budget_abstains(self):
        result = induce_operator_ast(
            self.train, self.train_labels, max_candidates=2)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reason"], "CANDIDATE_BUDGET_EXCEEDED")

    def test_no_negative_labels_rejected(self):
        with self.assertRaises(ValueError):
            induce_operator_ast(self.train, self.train_labels[:3])

    def test_validation_rejects_tampering(self):
        rule = self.rule()
        rule["ast"]["right"]["predicate"] = "fabricated"
        with self.assertRaises(ValueError):
            validate_operator_ast(self.train, rule, self.held, self.held_labels)

    def test_persistence_rejects_post_validation_mutation(self):
        rule = self.rule()
        assessment = validate_operator_ast(
            self.train, rule, self.held, self.held_labels)
        rule["ast"]["right"]["predicate"] = "tampered"
        with self.assertRaises(ValueError):
            compile_operator_lens(self.held, rule=rule, assessment=assessment,
                                  lens_id="unsafe", purpose="verification")

    def test_store_records_candidate_only(self):
        rule = self.rule()
        assessment = validate_operator_ast(
            self.train, rule, self.held, self.held_labels)
        lens = compile_operator_lens(
            self.held, rule=rule, assessment=assessment,
            lens_id="mixed-grammar", purpose="labeled-relations")
        db = sqlite3.connect(":memory:")
        store = SemanticStore(db)
        store.initialize()
        receipt = persist_lens(
            store, lens=lens, source_id="held-graph", revision="v1",
            packspec_digest="unverified-packspec")
        self.assertEqual(receipt["admission"], "INCONCLUSIVE")
        self.assertEqual(
            store.object_version("rct:lens:mixed-grammar", "v1")
            ["evaluation"]["finite_graph_verdict"], "SAT")

    def test_identical_training_heldout_rejected(self):
        with self.assertRaises(ValueError):
            validate_operator_ast(
                self.train, self.rule(), self.train, self.train_labels)


if __name__ == "__main__":
    unittest.main()
