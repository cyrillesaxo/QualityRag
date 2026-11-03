"""v1.4 declarative typed AST search, heldout witnesses and SemanticStore."""
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rct_typed_grammar import (
    induce_typed_rule, validate_typed_rule, compile_typed_lens)
from rct_lens import persist_lens
from store import SemanticStore


def source(prefix="", *, invalid_negative=False):
    facts=[]; labels=[]
    def add(s,p,o):
        facts.append({"id":f"{prefix}fact-{len(facts)}",
                      "subject":f"{prefix}{s}","predicate":p,"object":f"{prefix}{o}",
                      "source_ref":f"{prefix}input#{len(facts)}"})
    for n in range(3):
        add(f"subject-{n}","p",f"middle-{n}")
        add(f"middle-{n}","q",f"target-{n}")
        add(f"subject-{n}","r",f"target-{n}")
        labels.append({"subject":f"{prefix}subject-{n}",
                       "object":f"{prefix}target-{n}","positive":True,
                       "source_ref":f"label#{n}"})
    add("negative-path","p","middle-negative")
    add("middle-negative","q","target-negative")
    labels.append({"subject":f"{prefix}negative-path","object":f"{prefix}target-negative",
                   "positive":False,"source_ref":"label#no-r"})
    add("negative-edge","r","target-negative2")
    labels.append({"subject":f"{prefix}negative-edge","object":f"{prefix}target-negative2",
                   "positive":False,"source_ref":"label#no-pq"})
    if invalid_negative:
        add("negative-path","r","target-negative")
    return {"schema":"rct.structured-ast/v1","facts":facts},labels


def grammar():
    return {"schema":"rct.typed-operator-grammar/v1.4",
            "predicate_types":{"p":["object","middle"],"q":["middle","target"],
                               "r":["object","target"]},
            "operators":["EDGE","PATH","AND"],
            "max_ast_nodes":5,"max_candidates":400}


class TestTypedGrammar(unittest.TestCase):
    def setUp(self):
        self.train,self.labels=source("train-")
        self.heldout,self.heldout_labels=source("held-")
        self.spec=grammar()

    def candidate(self):
        return induce_typed_rule(self.train,self.labels,self.spec)

    def test_synthesizes_type_correct_compositional_rule(self):
        r=self.candidate()
        self.assertEqual(r["status"],"CANDIDATE")
        self.assertEqual(r["ast"]["op"],"AND")
        self.assertEqual(r["ast_nodes"],5)
        self.assertEqual(r["result_type"],["object","target"])
        self.assertEqual({r["ast"]["left"]["op"],r["ast"]["right"]["op"]},
                         {"PATH","EDGE"})
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")

    def test_heldout_and_counterexample(self):
        r=self.candidate()
        good=validate_typed_rule(self.train,r,self.heldout,self.heldout_labels,self.spec)
        self.assertEqual(good["finite_graph_verdict"],"SAT")
        self.assertEqual(len(good["witnesses"]),5)
        bad,labels=source("held-",invalid_negative=True)
        failed=validate_typed_rule(self.train,r,bad,labels,self.spec)
        self.assertEqual(failed["finite_graph_verdict"],"UNSAT")
        self.assertEqual(failed["status"],"COUNTEREXAMPLE")
        self.assertEqual(len(failed["counterexamples"]),1)

    def test_declared_type_blocks_invalid_path(self):
        spec=grammar()
        spec["predicate_types"]["q"]=["unrelated","target"]
        r=induce_typed_rule(self.train,self.labels,spec)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"NO_CONSISTENT_TYPED_AST")

    def test_grammar_limits_abstain(self):
        spec=grammar();spec["max_ast_nodes"]=3
        r=induce_typed_rule(self.train,self.labels,spec)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"NO_CONSISTENT_TYPED_AST")
        spec=grammar();spec["max_candidates"]=2
        r=induce_typed_rule(self.train,self.labels,spec)
        self.assertEqual(r["reason"],"CANDIDATE_BUDGET_EXCEEDED")

    def test_tampering_and_changed_grammar_rejected(self):
        r=self.candidate()
        tampered=dict(r);tampered["result_type"]=["fake","type"]
        with self.assertRaises(ValueError):
            validate_typed_rule(self.train,tampered,self.heldout,self.heldout_labels,self.spec)
        spec=grammar();spec["max_ast_nodes"]=7
        with self.assertRaises(ValueError):
            validate_typed_rule(self.train,r,self.heldout,self.heldout_labels,spec)

    def test_actual_store_remains_non_admitted(self):
        r=self.candidate()
        assessment=validate_typed_rule(
            self.train,r,self.heldout,self.heldout_labels,self.spec)
        lens=compile_typed_lens(self.heldout,rule=r,assessment=assessment,
                                grammar=self.spec,lens_id="typed-v14",
                                purpose="labeled-object-target")
        db=sqlite3.connect(":memory:")
        store=SemanticStore(db);store.initialize()
        receipt=persist_lens(store,lens=lens,source_id="structured",
                             revision="v1",packspec_digest="unverified")
        self.assertEqual(receipt["admission"],"INCONCLUSIVE")
        self.assertEqual(store.object_version("rct:lens:typed-v14","v1")
                         ["candidate_grammar"]["ast_nodes"],5)

    def test_untyped_source_predicate_rejected(self):
        wrong=source("train-")[0]
        wrong["facts"][0]["predicate"]="unknown_predicate"
        with self.assertRaises(ValueError):
            induce_typed_rule(wrong,self.labels,self.spec)


if __name__=="__main__":
    unittest.main()
