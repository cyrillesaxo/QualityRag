"""Finite four-regime experiment on the SAME user-supplied evidence questions.

R1 raw textual lookup; R2 typed Codex lexical index; R3 reviewed-input
candidate relation graph; R4 finite evidence-presence requirements and
conservative refusal. No system authenticates review, meaning, or PackSpec
signatures. Graph presence cannot establish factual truth. This experiment
compares *affordances*, not equivalent-capability competing products.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from semantic_codex import CodexError, compile_source
from directory_codex import persist_codex, search_store
from query import query_context
from store import SemanticStore, digest

SCHEMA="qualityrag.four-regime-contrast/v1.0"
MAX_SOURCES=40
MAX_QUERIES=20
REGIMES=("R1_RAW_TEXT","R2_CODEX_LEXICAL","R3_TYPED_RELATION","R4_WITNESS_REQUIREMENTS")


def _validate(manifest):
    if not isinstance(manifest,dict) or set(manifest)!={"schema","sources","relations","witnesses","questions"} or manifest["schema"]!="qualityrag.four-regime-input/v1.0":
        raise CodexError("Invalid four-regime manifest")
    sources=manifest["sources"]
    questions=manifest["questions"]
    relations=manifest["relations"]
    witnesses=manifest["witnesses"]
    if (not isinstance(sources,list) or not 2<=len(sources)<=MAX_SOURCES
        or not isinstance(questions,list) or not 1<=len(questions)<=MAX_QUERIES
        or not isinstance(relations,list) or len(relations)>100
        or not isinstance(witnesses,list) or len(witnesses)>100):
        raise CodexError("Manifest exceeds finite budgets")
    source_ids=set()
    for s in sources:
        if (not isinstance(s,dict) or set(s)!={"id","text"} or
                not isinstance(s["id"],str) or not s["id"].isalnum() or len(s["id"])>50 or
                s["id"] in source_ids or not isinstance(s["text"],str)
                or not 1<=len(s["text"])<=1000):
            raise CodexError("Invalid unique text source")
        source_ids.add(s["id"])
    relations_seen=set()
    for edge in relations:
        if (not isinstance(edge,dict) or set(edge)!={"from","to","relation"} or
            edge["from"] not in source_ids or edge["to"] not in source_ids or
            not isinstance(edge["relation"],str) or not edge["relation"].isupper()
            or not edge["relation"].replace("_","").isalpha() or
            len(edge["relation"])>48):
            raise CodexError("Invalid typed relation")
        key=(edge["from"],edge["to"],edge["relation"])
        if key in relations_seen:
            raise CodexError("Duplicate typed relation")
        relations_seen.add(key)
    witness_seen=set()
    for witness in witnesses:
        if (not isinstance(witness,dict) or set(witness)!={"target","source"} or
            witness["target"] not in source_ids or witness["source"] not in source_ids):
            raise CodexError("Invalid candidate witness")
        key=(witness["target"],witness["source"])
        if key in witness_seen:
            raise CodexError("Duplicate candidate witness")
        witness_seen.add(key)
    questions_seen=set()
    for q in questions:
        if (not isinstance(q,dict) or set(q)!={"id","term","relation","expected_targets","required_witnesses"}
            or not isinstance(q["id"],str) or not q["id"].isalnum()
            or q["id"] in questions_seen
            or not isinstance(q["term"],str) or not 1<=len(q["term"])<=100
            or not isinstance(q["relation"],str) or not q["relation"].isupper()
            or q["relation"] not in {e["relation"] for e in relations}
            or not isinstance(q["expected_targets"],list)
            or not isinstance(q["required_witnesses"],list)
            or len(q["expected_targets"])>MAX_SOURCES
            or len(q["required_witnesses"])>MAX_SOURCES
            or len(set(q["expected_targets"]))!=len(q["expected_targets"])
            or len(set(q["required_witnesses"]))!=len(q["required_witnesses"])
            or any(x not in source_ids for x in q["expected_targets"]+q["required_witnesses"])):
            raise CodexError("Malformed reviewed question obligations")
        questions_seen.add(q["id"])
    return sources,questions


def _stamp(fn):
    start=perf_counter_ns()
    value=fn()
    return value,(perf_counter_ns()-start)/1e6


def _summary(samples):
    ordered=sorted(samples)
    return {"count":len(ordered),"median_ms":round(median(ordered),6),
            "p95_nearest_rank_ms":round(ordered[math.ceil(.95*len(ordered))-1],6)}


def run_regime_contrast(manifest: dict, *, repetitions: int = 3, principal: str,
                        authorize_source) -> dict:
    sources,questions=_validate(manifest)
    if (type(repetitions) is not int or not 1<=repetitions<=20
            or not isinstance(principal,str) or not principal
            or not callable(authorize_source)):
        raise CodexError("Invalid bounded experiment or missing caller policy")
    sid=lambda key:"regime/"+key+".json"
    rev={}
    serialized={}
    for s in sources:
        data=json.dumps({"text":s["text"]},sort_keys=True).encode()
        serialized[s["id"]]=data
        rev[s["id"]]=sha256(data).hexdigest()
        if not authorize_source(principal,sid(s["id"]),rev[s["id"]]):
            raise PermissionError("Source outside reviewed authorized test scope")
    with TemporaryDirectory(prefix="qualityrag-regimes-") as tmp:
        path=Path(tmp)/"regimes.sqlite3"
        conn=sqlite3.connect(path)
        store=SemanticStore(conn)
        store.initialize()
        try:
            def build_r2():
                for s in sources:
                    artifact=compile_source(serialized[s["id"]],source_id=sid(s["id"]),
                                            revision=rev[s["id"]],format="json")
                    persist_codex(store,artifact)
            _,r2_index_ms=_stamp(build_r2)
            r2_bytes=path.stat().st_size
            def build_r3():
                for s in sources:
                    store.add_object("node:"+s["id"],rev[s["id"]],sid(s["id"]),
                                     rev[s["id"]],"BENCHMARK_CANDIDATE",
                                     {"id":s["id"],"review":"CALLER_SUPPLIED_UNVERIFIED"})
                for i,edge in enumerate(manifest["relations"]):
                    store.add_edge("relation:"+str(i),"KNOWLEDGE",
                        "node:"+edge["from"],rev[edge["from"]],
                        "node:"+edge["to"],rev[edge["to"]],edge["relation"],
                        {"review":"CALLER_SUPPLIED_UNVERIFIED"})
            _,r3_index_ms=_stamp(build_r3)
            r3_bytes=path.stat().st_size
            def build_r4():
                for i,w in enumerate(manifest["witnesses"]):
                    store.add_edge("witness:"+str(i),"WITNESS",
                        "node:"+w["target"],rev[w["target"]],
                        "node:"+w["source"],rev[w["source"]],"DERIVED_WITNESS",
                        {"independent":False,"verification":"NOT_PERFORMED"})
            _,r4_index_ms=_stamp(build_r4)
            conn.commit()
            r4_bytes=path.stat().st_size
            auth_obj=lambda p,oid,r: (p==principal and isinstance(oid,str)
                      and oid.startswith("node:") and oid[5:] in rev
                      and rev[oid[5:]]==r and
                      authorize_source(p,sid(oid[5:]),r))

            def seeds_from_raw(term):
                return [s["id"] for s in sources if term.casefold() in s["text"].casefold()]
            def seeds_from_codex(term):
                result=search_store(store,term,namespace="regime",principal=principal,
                       authorize_source=authorize_source,max_hits=100,max_records=5000)
                if result["truncated"]:
                    raise CodexError("Truncated lexical candidate pool")
                return [h["source_id"][len("regime/"):-len(".json")] for h in result["hits"]]

            def targets(seeds, relation):
                output=set()
                for seed in seeds:
                    context=query_context(store,principal=principal,authorize=auth_obj,
                        object_id="node:"+seed,revision=rev[seed],
                        max_hops=1,max_nodes=41,max_edges=100,
                        layers=("KNOWLEDGE",))
                    if context.get("status")!="BOUNDED_CONTEXT" or context["limits"]["truncated"]:
                        raise CodexError("Typed candidate traversal incomplete")
                    for edge in context["edges"]:
                        if edge["relation"]==relation:
                            output.add(edge["to_id"][len("node:"):])
                return sorted(output)

            def evidence_presence(target, required):
                context=query_context(store,principal=principal,authorize=auth_obj,
                    object_id="node:"+target,revision=rev[target],
                    max_hops=1,max_nodes=41,max_edges=100,layers=("WITNESS",))
                if context.get("status")!="BOUNDED_CONTEXT" or context["limits"]["truncated"]:
                    raise CodexError("Finite evidence-presence traversal incomplete")
                witnessed={e["to_id"][len("node:"):] for e in context["edges"]
                           if e["relation"]=="DERIVED_WITNESS"}
                return set(required).issubset(witnessed)

            times={regime:[] for regime in REGIMES}
            results=[]
            for repeat in range(repetitions):
                for question in questions:
                    term,relation=question["term"],question["relation"]
                    seed_raw,t1=_stamp(lambda:seeds_from_raw(term))
                    seed_codex,t2=_stamp(lambda:seeds_from_codex(term))
                    if set(seed_raw)!=set(seed_codex):
                        raise CodexError("Baseline and Codex seeds disagree")
                    target_set,t3=_stamp(lambda:targets(seed_codex,relation))
                    def governed():
                        if not target_set:
                            return {"candidates":[],"gate":"NO_RELATION_CANDIDATES"}
                        present=all(evidence_presence(target,question["required_witnesses"])
                                    for target in target_set)
                        return {"candidates":target_set if present else [],
                                "gate":"INCONCLUSIVE_SOURCE_AUTHENTICITY" if present
                                       else "REFUSE_MISSING_WITNESS_PRESENCE"}
                    governed_result,t4=_stamp(governed)
                    for name,elapsed in zip(REGIMES,(t1,t2,t2+t3,t2+t3+t4)):
                        times[name].append(elapsed)
                    truth=set(question["expected_targets"])
                    matched=sorted(truth.intersection(target_set))
                    results.append({
                        "question_id":question["id"],"repetition":repeat,
                        "expected_targets_count":len(truth),
                        "r1_seed_count":len(seed_raw),"r2_seed_count":len(seed_codex),
                        "r3_relation_candidate_count":len(target_set),
                        "r3_finite_candidate_recall":len(matched)/len(truth) if truth else None,
                        "r4_gate":governed_result["gate"],
                        "r4_released_results":0,  # no verified source authority
                        "admission":"INCONCLUSIVE",
                    })
            return {
                "schema":SCHEMA,
                "manifest_fingerprint":digest(manifest),
                "labels_authenticity":"CALLER_SUPPLIED_UNVERIFIED",
                "scope":"FINITE_TYPED_TEXT_FIXTURE_NOT_MULTIMODAL_PARITY",
                "regimes":[
                    {"id":"R1_RAW_TEXT","scope":"SEED_TEXT_ONLY_NO_RELATION"},
                    {"id":"R2_CODEX_LEXICAL","scope":"INDEXED_SEED_TEXT_ONLY"},
                    {"id":"R3_TYPED_RELATION","scope":"CANDIDATE_RELATION_ONLY"},
                    {"id":"R4_WITNESS_REQUIREMENTS","scope":"FINITE_EVIDENCE_PRESENCE_NOT_AUTHENTICATION"},
                ],
                "index_build_ms":{"R1_RAW_TEXT":0.0,
                                  "R2_CODEX_LEXICAL":round(r2_index_ms,6),
                                  "R3_TYPED_RELATION_ADDITIONAL":round(r3_index_ms,6),
                                  "R4_WITNESS_ADDITIONAL":round(r4_index_ms,6)},
                "database_bytes":{"R1_RAW_TEXT":"NO_DATABASE",
                                  "R2_CODEX_LEXICAL":r2_bytes,
                                  "R3_TYPED_RELATION":r3_bytes,
                                  "R4_WITNESS_REQUIREMENTS":r4_bytes},
                "query_latency":{name:_summary(values) for name,values in times.items()},
                "question_results":results,
                "repetitions":repetitions,
                "semantic_equivalence":"NOT_ESTABLISHED_DIFFERENT_REGIME_CAPABILITIES",
                "source_authenticity":"UNVERIFIED",
                "trusted_packspec_evaluation":"NOT_PERFORMED",
                "full_lifecycle_cost":"NOT_ESTABLISHED",
                "admission":"INCONCLUSIVE","can_generate":False,
            }
        finally:
            conn.close()
