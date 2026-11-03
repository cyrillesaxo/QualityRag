"""One-command reproducible RCT candidate demonstration.

Run from repository root:
  python tools/semantic_store/rct_demo.py
No network, secrets, or customer data. The result is ALWAYS a research candidate.
"""
from __future__ import annotations
import json

from rct_end_to_end import run_structural_pipeline


def fixture(prefix: str) -> tuple[dict, list[dict]]:
    facts, labels = [], []
    def add(subject, predicate, object):
        facts.append({"id":prefix+str(len(facts)), "subject":prefix+subject,
                      "predicate":predicate,"object":prefix+object,
                      "source_ref":"synthetic#"+prefix+str(len(facts))})
    for index in range(3):
        add("case"+str(index),"p","middle"+str(index))
        add("middle"+str(index),"q","answer"+str(index))
        add("case"+str(index),"r","answer"+str(index))
        add("case"+str(index),"context","noise"+str(index))
        labels.append({"subject":prefix+"case"+str(index),
                       "object":prefix+"answer"+str(index),
                       "positive":True,"source_ref":"label#"+str(index)})
    add("negative-path","p","middle-n")
    add("middle-n","q","answer-n")
    add("negative-guard","r","answer-g")
    labels.extend([
        {"subject":prefix+"negative-path","object":prefix+"answer-n",
         "positive":False,"source_ref":"label#no-r"},
        {"subject":prefix+"negative-guard","object":prefix+"answer-g",
         "positive":False,"source_ref":"label#no-pq"},
    ])
    return {"schema":"rct.structured-ast/v1","facts":facts},labels


def run_demo() -> dict:
    train, train_labels = fixture("train-")
    held, held_labels = fixture("held-")
    grammar={"schema":"rct.typed-operator-grammar/v1.4",
             "predicate_types":{
                 "p":["object","middle"],"q":["middle","target"],
                 "r":["object","target"],"context":["object","noise"]},
             "operators":["EDGE","PATH","AND"],
             "max_ast_nodes":5,"max_candidates":500}
    outcome=run_structural_pipeline(
        train,train_labels,held,held_labels,grammar,
        purpose="finite-classification-training",lens_id="rct-research-demo",
        required_predicates=["p","q","r"],
        allowed_omission_predicates=["context"])
    if outcome["stage"] != "RESEARCH_CANDIDATE":
        return {"status":outcome["status"],"can_generate":False,
                "qualityrag_admission":"INCONCLUSIVE"}
    lens=outcome["purpose_lens"]
    return {
        "schema":"rct.reproducible-demo/v2",
        "status":outcome["status"],
        "grammar_ast":outcome["grammar_candidate"]["ast"],
        "source_facts":lens["source_fact_count"],
        "active_lens_facts":lens["selected_fact_count"],
        "locally_omitted_fact_ids":lens["omitted_fact_ids"],
        "finite_relation_verdict":outcome["conservation"]["finite_structural_verdict"],
        "canonical_source_reconstructed":outcome["reconstruction"]
            ["exact_canonical_round_trip"],
        "native_ff_rct":False,
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "unresolved":outcome["blockers"],
    }


if __name__=="__main__":
    print(json.dumps(run_demo(),indent=2,sort_keys=True))
