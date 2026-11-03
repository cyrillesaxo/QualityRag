"""Bounded data-driven composition grammar proposals over typed AST facts.

The operator template is a two-hop relational join. Predicate PAIRS are mined
from observed data rather than selected from a catalog of domain-specific rules.
This proves *finite graph answer equivalence only*, not semantic equivalence,
causal meaning, global completeness, or algorithmic novelty.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from rct_grammar import _validate
from store import digest

SCHEMA = "rct.composition-candidate/v0.8"

def _index(facts: list[dict]) -> dict[str, list[dict]]:
    idx = defaultdict(list)
    for f in facts:
        idx[f["subject"]].append(f)
    return idx

def _derive(facts: list[dict], first: str, second: str) -> dict[tuple[str,str], list[list[str]]]:
    idx = _index(facts)
    out = defaultdict(list)
    for left in facts:
        if left["predicate"] != first:
            continue
        for right in idx.get(left["object"], []):
            if right["predicate"] == second:
                out[(left["subject"], right["object"])].append([left["id"],right["id"]])
    return {key: sorted(paths) for key, paths in sorted(out.items())}

def propose_compositions(source: dict, *, max_candidates: int = 64,
                         minimum_distinct_pairs: int = 2) -> list[dict]:
    """Mine recurring predicate compositions from an authored typed graph.

    Each proposal is a structural candidate with support paths and an
    unverified natural-language interpretation. Does not infer transitivity.
    """
    facts = _validate(source)
    if (type(max_candidates) is not int or not 1 <= max_candidates <= 256
        or type(minimum_distinct_pairs) is not int
        or not 1 <= minimum_distinct_pairs <= 100):
        raise ValueError("Invalid bounded search limits")
    idx = _index(facts)
    pairs = set()
    for left in facts:
        for right in idx.get(left["object"], []):
            pairs.add((left["predicate"],right["predicate"]))
    result=[]
    for p1,p2 in sorted(pairs):
        derived = _derive(facts,p1,p2)
        if len(derived) < minimum_distinct_pairs:
            continue
        support = sorted({eid for paths in derived.values() for path in paths for eid in path})
        proposal = {
            "schema":SCHEMA,
            "operator":"COMPOSE_TWO_HOP",
            "predicate_sequence":[p1,p2],
            "output_predicate":f"derived:{digest([p1,p2])[:16]}",
            "support_fact_ids":support,
            "support_source_sha256":digest(source),
            "distinct_pairs":len(derived),
            "evaluation":"CANDIDATE",
            "qualityrag_admission":"INCONCLUSIVE",
            "semantics":"STRUCTURAL_PATH_ONLY",
        }
        proposal["fingerprint"]=digest(proposal)
        result.append(proposal)
    return sorted(result,key=lambda c:(-c["distinct_pairs"],c["predicate_sequence"]))[:max_candidates]

def verify_composition(training: dict, validation: dict, candidate: dict,
                       *, query_budget: int=100, evaluation_budget: int=100000) -> dict:
    """Check proposed materialization against independent finite-graph reference.

    All source facts in validation are inspected through the direct join; no
    evaluation on only preselected positive samples. The test is exact for this
    supplied finite graph, with no claim about unsupplied real-world facts.
    """
    train_facts=_validate(training)
    valid_facts=_validate(validation)
    if (type(query_budget) is not int or not 1 <= query_budget <= 100000
            or type(evaluation_budget) is not int or not 1 <= evaluation_budget <= 1000000):
        raise ValueError("Invalid evaluation bounds")
    body=dict(candidate) if isinstance(candidate,dict) else {}
    fingerprint=body.pop("fingerprint",None)
    if (body.get("schema")!=SCHEMA or body.get("operator")!="COMPOSE_TWO_HOP"
        or fingerprint!=digest(body)
        or body.get("support_source_sha256")!=digest(training)
        or body.get("qualityrag_admission")!="INCONCLUSIVE"):
        raise ValueError("Untrusted or modified proposal")
    sequence=body.get("predicate_sequence")
    if not isinstance(sequence,list) or len(sequence)!=2 or any(not isinstance(x,str) for x in sequence):
        raise ValueError("Invalid predicate sequence")
    first,second=sequence
    training_pairs=_derive(train_facts,first,second)
    # Only structural materialization: if source changes, version is required.
    validation_pairs=_derive(valid_facts,first,second)
    subjects=sorted({f["subject"] for f in valid_facts} | {f["object"] for f in valid_facts})
    if len(subjects)*len(valid_facts)>evaluation_budget:
        return {"status":"UNKNOWN","reason":"EVALUATION_BUDGET_EXCEEDED",
                "qualityrag_admission":"INCONCLUSIVE"}
    if len(subjects)>query_budget:
        return {"status":"UNKNOWN","reason":"QUERY_BUDGET_EXCEEDED",
                "qualityrag_admission":"INCONCLUSIVE"}
    # Independent reference: enumerate every source's two-hop evidence directly.
    reference={}
    idx=_index(valid_facts)
    for subject in subjects:
        destinations=set()
        for first_edge in idx.get(subject,[]):
            if first_edge["predicate"]!=first: continue
            for next_edge in idx.get(first_edge["object"],[]):
                if next_edge["predicate"]==second:
                    destinations.add(next_edge["object"])
        reference[subject]=sorted(destinations)
    materialized=defaultdict(set)
    for (src,dst),paths in validation_pairs.items():
        materialized[src].add(dst)
    actual={subject:sorted(materialized[subject]) for subject in subjects}
    matches=actual==reference
    result={
        "schema":"rct.composition-evaluation/v0.8",
        "candidate_fingerprint":fingerprint,
        "training_pairs":len(training_pairs),
        "validation_pairs":len(validation_pairs),
        "evaluation_subjects":len(subjects),
        "exact_finite_graph_match":matches,
        "structural_verdict":"SAT" if matches else "UNSAT",
        "qualityrag_admission":"INCONCLUSIVE",
        "validation_source_sha256":digest(validation),
        "trained_on_validation":False,
        "validation_claim":"FINITE_GRAPH_REACHABILITY_ONLY",
        "derived_edges":[
            {"subject":s,"predicate":body["output_predicate"],"object":d,
             "support_fact_ids":paths,
             "source_ref_status":"UNVERIFIED"}
            for (s,d),paths in validation_pairs.items()
        ],
        "cost_proxy":{
            "construction_required":True,
            "materialized_pair_count":len(validation_pairs),
            "query_subject_count":len(subjects),
            "measured_cpu_time":False,
            "measured_memory":False,
        },
    }
    result["fingerprint"]=digest(result)
    return result

def compile_composition_lens(training: dict, validation: dict, candidate:dict,
                             *, lens_id:str, purpose:str) -> dict:
    """Create a candidate-only lens for persistence in the existing SemanticStore."""
    from rct_grammar import _ident
    if not _ident(lens_id) or not _ident(purpose):
        raise ValueError("Invalid lens metadata")
    assessment=verify_composition(training,validation,candidate)
    result={
        "schema":"rct.source-lens/v0.6",
        "discovery_schema":SCHEMA,
        "lens_id":lens_id,
        "purpose":purpose,
        "source_sha256":digest(validation),
        "required":["structural-composition-evaluation"],
        "permitted_omissions":[],
        "candidate_claims":[{"source_fact_ids":e["support_fact_ids"],
                             "status":"UNVERIFIED_SOURCE_CLAIM"} for e in assessment.get("derived_edges",[])],
        "candidate_grammar":candidate,
        "evaluation":assessment,
        "unresolved":([] if assessment.get("structural_verdict")=="SAT"
                      else ["structural_evaluation"]),
        "local_coverage":"FINITE_STRUCTURE_CHECKED" if assessment.get("structural_verdict")=="SAT" else "UNKNOWN",
        "qualityrag_admission":"INCONCLUSIVE",
        "source_authenticity":"UNVERIFIED",
        "packspec_completeness":"UNKNOWN",
        "grammar":"BOUNDED_DATA_MINED_PREDICATE_COMPOSITION",
        "limitations":["Equivalent only under finite-graph structural path semantics",
                       "No proof of natural-language or domain truth",
                       "Original source must be retained for other query families",
                       "No measured end-to-end cost advantage"],
    }
    result["fingerprint"]=digest(result)
    return result
