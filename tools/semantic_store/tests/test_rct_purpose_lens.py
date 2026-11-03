"""v1.5 purpose-scoped omission tests against the real SemanticStore."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_purpose_lens import make_contract, compile_purpose_lens
from rct_typed_grammar import induce_typed_rule, validate_typed_rule
from rct_lens import persist_lens
from store import SemanticStore


def fixture(prefix):
    facts, labels = [], []
    def edge(s, p, o):
        facts.append({"id": f"{prefix}f{len(facts)}",
                      "subject":f"{prefix}{s}", "predicate":p,
                      "object":f"{prefix}{o}", "source_ref":f"ref#{len(facts)}"})
    for n in range(3):
        edge(f"case{n}", "p", f"middle{n}")
        edge(f"middle{n}", "q", f"answer{n}")
        edge(f"case{n}", "r", f"answer{n}")
        edge(f"case{n}", "context", f"noise{n}")
        labels.append({"subject":f"{prefix}case{n}","object":f"{prefix}answer{n}",
                       "positive":True,"source_ref":f"label#{n}"})
    edge("negative-path","p","middle-n")
    edge("middle-n","q","answer-n")
    edge("negative-guard","r","answer-g")
    edge("negative-guard","context","noise-g")
    labels.extend([
        {"subject":f"{prefix}negative-path","object":f"{prefix}answer-n",
         "positive":False,"source_ref":"label#no-r"},
        {"subject":f"{prefix}negative-guard","object":f"{prefix}answer-g",
         "positive":False,"source_ref":"label#no-pq"},
    ])
    return {"schema":"rct.structured-ast/v1","facts":facts},labels


def grammar():
    return {"schema":"rct.typed-operator-grammar/v1.4",
            "predicate_types":{"p":["object","middle"],"q":["middle","target"],
                               "r":["object","target"],"context":["object","noise"]},
            "operators":["EDGE","PATH","AND"],
            "max_ast_nodes":5,"max_candidates":500}


class TestPurposeLens(unittest.TestCase):
    def setUp(self):
        self.train,self.train_labels=fixture("train-")
        self.held,self.labels=fixture("held-")
        self.spec=grammar()
        # 4 predicates increase enumeration; select a sufficiently bounded search.
        self.rule=induce_typed_rule(self.train,self.train_labels,self.spec)
        self.assertEqual(self.rule["status"],"CANDIDATE")
        self.assessment=validate_typed_rule(
            self.train,self.rule,self.held,self.labels,self.spec)
        self.assertEqual(self.assessment["finite_graph_verdict"],"SAT")

    def contract(self, required=None, optional=None):
        return make_contract(
            self.held,self.labels,purpose="classification-training",
            required_predicates=required or ["p","q","r"],
            allowed_omission_predicates=optional if optional is not None else ["context"])

    def compile(self,contract):
        return compile_purpose_lens(
            self.held,self.labels,grammar=self.spec,rule=self.rule,
            assessment=self.assessment,contract=contract,lens_id="purpose-v15")

    def test_governed_candidate_omits_only_unprotected_context(self):
        lens=self.compile(self.contract())
        self.assertEqual(lens["source_fact_count"]-lens["selected_fact_count"],4)
        self.assertEqual(len(lens["omitted_fact_ids"]),4)
        self.assertTrue(all(
            f["predicate"]=="context" for f in self.held["facts"]
            if f["id"] in lens["omitted_fact_ids"]))
        self.assertFalse(set(lens["omitted_fact_ids"]) & set(lens["protected_fact_ids"]))
        self.assertEqual(lens["local_preservation"]["label_count"],5)
        self.assertEqual(lens["qualityrag_admission"],"INCONCLUSIVE")
        self.assertEqual(lens["packspec_completeness"],"UNKNOWN")

    def test_witness_fact_not_omitted_even_when_predicate_is_optional(self):
        lens=self.compile(self.contract(required=["p","q"],optional=["r","context"]))
        positives={fid for row in self.assessment["witnesses"] if row["label"]=="POSITIVE"
                   for fid in row["fact_witness"]}
        self.assertTrue(positives <= set(lens["protected_fact_ids"]))
        self.assertFalse(positives & set(lens["omitted_fact_ids"]))

    def test_required_optional_conflict_rejected(self):
        with self.assertRaises(ValueError):
            self.contract(required=["p","q","r"],optional=["r","context"])

    def test_source_revisions_cannot_reuse_old_contract(self):
        changed={"schema":self.held["schema"],
                 "facts":[dict(f) for f in self.held["facts"]]}
        changed["facts"].append({"id":"new","subject":"x","object":"y",
                                "predicate":"context","source_ref":"ref#new"})
        with self.assertRaises(ValueError):
            compile_purpose_lens(
                changed,self.labels,grammar=self.spec,rule=self.rule,
                assessment=self.assessment,contract=self.contract(),lens_id="stale")

    def test_tampered_policy_rejected(self):
        contract=self.contract()
        contract["allowed_omission_predicates"].append("r")
        with self.assertRaises(ValueError):
            self.compile(contract)

    def test_changed_labels_rejected(self):
        labels=[dict(row) for row in self.labels]
        labels[-1]["positive"]=True
        with self.assertRaises(ValueError):
            compile_purpose_lens(self.held,labels,grammar=self.spec,
                 rule=self.rule,assessment=self.assessment,
                 contract=self.contract(),lens_id="stale-labels")

    def test_persistence_remains_inconclusive(self):
        lens=self.compile(self.contract())
        db=sqlite3.connect(":memory:")
        store=SemanticStore(db)
        store.initialize()
        result=persist_lens(store,lens=lens,source_id="purpose-source",
                            revision="v1",packspec_digest="experimental-contract")
        self.assertEqual(result["admission"],"INCONCLUSIVE")
        stored=store.object_version("rct:lens:purpose-v15","v1")
        self.assertEqual(stored["omitted_fact_ids"],lens["omitted_fact_ids"])
        self.assertEqual(
            db.execute("SELECT verdict FROM admission_receipts").fetchone()[0],
            "INCONCLUSIVE")

if __name__=="__main__":
    unittest.main()
