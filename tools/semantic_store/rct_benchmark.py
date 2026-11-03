"""RCT v0.9 workload experiment: direct SQL vs materialized SQL vs candidate lens.

Measurements are exploratory. SQL and Python have different execution overheads.
No semantic admission, innovation proof, or claimed RCT superiority.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import sqlite3
from statistics import median
from time import perf_counter_ns
from typing import Any

from rct_synthesis import propose_compositions, verify_composition
from store import digest

BENCHMARK_SCHEMA = "rct.workload-benchmark/v0.9"
CONTRACT_SCHEMA = "rct.workload-contract/v0.9"

def make_fixture(*, entities: int = 40, prefix: str = "") -> dict:
    if type(entities) is not int or not 4 <= entities <= 500:
        raise ValueError("entities must be between 4 and 500")
    facts = []
    for i in range(entities):
        # No precomputed derived edges in input.
        subject = f"{prefix}entity-{i}"
        middle = f"{prefix}group-{i // 4}"
        destination = f"{prefix}domain-{i // 16}"
        facts.append({"id":f"{prefix}left-{i}", "subject":subject,
                      "predicate":"projects_to","object":middle,"source_ref":f"fixture#{i}"})
        if i % 4 == 0:
            facts.append({"id":f"{prefix}right-{i}", "subject":middle,
                          "predicate":"belongs_to","object":destination,
                          "source_ref":f"fixture#{i}"})
    return {"schema":"rct.structured-ast/v1","facts":facts}

def _contract(source: dict, contract: dict) -> tuple[str, str, int]:
    if not isinstance(contract, dict) or contract.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("Explicit workload contract required")
    if (contract.get("query_family") != "two_hop_distinct_destinations"
            or contract.get("purpose") != "structural_reachability"
            or contract.get("source_sha256") != digest(source)
            or contract.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Unsupported scope or mismatched source")
    predicates = contract.get("predicates")
    if not (isinstance(predicates, list) and len(predicates) == 2
            and all(isinstance(p, str) and p for p in predicates)):
        raise ValueError("Exactly two predicates required")
    count = contract.get("repetitions")
    if type(count) is not int or not 1 <= count <= 500:
        raise ValueError("Invalid repetition count")
    return predicates[0], predicates[1], count

def make_contract(source: dict, *, repetitions: int = 8) -> dict:
    return {"schema":CONTRACT_SCHEMA, "purpose":"structural_reachability",
            "query_family":"two_hop_distinct_destinations",
            "predicates":["projects_to","belongs_to"],
            "source_sha256":digest(source),
            "repetitions":repetitions, "qualityrag_admission":"INCONCLUSIVE",
            "closure":"OPEN_WORLD_UNKNOWN",
            "omissions":"NOT_AUTHORIZED"}

def _measure(fn) -> tuple[Any, int]:
    started = perf_counter_ns()
    output = fn()
    return output, perf_counter_ns() - started

def _db(source: dict) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE facts (id TEXT PRIMARY KEY, subject TEXT, predicate TEXT, object TEXT)")
    db.executemany("INSERT INTO facts VALUES(?,?,?,?)",
        [(f["id"],f["subject"],f["predicate"],f["object"]) for f in source["facts"]])
    db.execute("CREATE INDEX ix_facts_source ON facts(subject,predicate)")
    db.execute("CREATE INDEX ix_facts_object ON facts(object,predicate)")
    return db

def _sql_direct(db, subject, first, second):
    return sorted(row[0] for row in db.execute(
        """SELECT DISTINCT r.object FROM facts l
           JOIN facts r ON l.object = r.subject
           WHERE l.subject = ? AND l.predicate = ? AND r.predicate = ?
           ORDER BY r.object""",(subject,first,second)))

def _sql_materialize(db, first, second):
    db.execute("DROP TABLE IF EXISTS derived")
    db.execute("""CREATE TABLE derived AS
                  SELECT DISTINCT l.subject AS subject, r.object AS object
                  FROM facts l JOIN facts r ON l.object = r.subject
                  WHERE l.predicate = ? AND r.predicate = ?""", (first,second))
    db.execute("CREATE INDEX ix_derived_subject ON derived(subject)")

def _sql_materialized(db, subject):
    return sorted(row[0] for row in db.execute(
        "SELECT object FROM derived WHERE subject=? ORDER BY object",(subject,)))

def _rct_materialize(training, source, first, second):
    candidates = propose_compositions(training,minimum_distinct_pairs=2)
    selected = next((p for p in candidates if p["predicate_sequence"] == [first,second]),None)
    if selected is None:
        raise ValueError("No eligible learned composition candidate")
    evaluation = verify_composition(training,source,selected,
        query_budget=100000,evaluation_budget=1000000)
    if evaluation.get("structural_verdict") != "SAT":
        raise ValueError("Finite structural equivalence was not established")
    index = defaultdict(set)
    for edge in evaluation["derived_edges"]:
        index[edge["subject"]].add(edge["object"])
    return {key:sorted(values) for key,values in index.items()}

def _run_queries(query, subjects, repetitions):
    checksums = []
    for _ in range(repetitions):
        checksums.append(digest([query(subject) for subject in subjects]))
    return checksums

def run_benchmark(source: dict, training: dict, contract: dict,
                  *, trials: int = 3) -> dict[str, Any]:
    first,second,repetitions = _contract(source,contract)
    if type(trials) is not int or not 1 <= trials <= 15:
        raise ValueError("trials must be 1-15")
    if digest(source) == digest(training):
        raise ValueError("Evaluation source must differ from training source")
    subjects = sorted({f["subject"] for f in source["facts"]})
    records=[]
    for trial in range(trials):
        db, load_ns = _measure(lambda:_db(source))
        try:
            direct_hashes, direct_ns = _measure(
                lambda:_run_queries(lambda s:_sql_direct(db,s,first,second),
                                    subjects,repetitions))
            _, sql_build_ns = _measure(lambda:_sql_materialize(db,first,second))
            sql_hashes,sql_ns = _measure(
                lambda:_run_queries(lambda s:_sql_materialized(db,s),
                                    subjects,repetitions))
            lens,lens_build_ns = _measure(
                lambda:_rct_materialize(training,source,first,second))
            lens_hashes,lens_ns = _measure(
                lambda:_run_queries(lambda s:lens.get(s,[]),subjects,repetitions))
            if not (direct_hashes == sql_hashes == lens_hashes):
                raise AssertionError("Query answer mismatch; benchmark invalid")
            records.append({
                "trial":trial+1,
                "source_load_and_index_ns":load_ns,
                "direct_sql":{"build_ns":0,"query_ns":direct_ns,"total_ns":load_ns+direct_ns},
                "materialized_sql":{"build_ns":sql_build_ns,"query_ns":sql_ns,
                                    "total_ns":load_ns+sql_build_ns+sql_ns},
                "candidate_lens":{"build_ns":lens_build_ns,"query_ns":lens_ns,
                                  "total_ns":load_ns+lens_build_ns+lens_ns},
                "output_sha256":direct_hashes[0],
                "verified_equal_for_declared_workload":True,
            })
        finally:
            db.close()
    summary = {name:{metric:median(r[name][metric] for r in records)
                     for metric in ("build_ns","query_ns","total_ns")}
               for name in ("direct_sql","materialized_sql","candidate_lens")}
    result={
        "schema":BENCHMARK_SCHEMA,
        "workload_contract_sha256":digest(contract),
        "validation_source_sha256":digest(source),
        "training_source_sha256":digest(training),
        "source_fact_count":len(source["facts"]),
        "queries_per_trial":len(subjects)*repetitions,
        "trial_count":trials,
        "measurement_unit":"perf_counter_ns",
        "verified_identical_answers":True,
        "medians":summary,
        "trials":records,
        "qualityrag_admission":"INCONCLUSIVE",
        "result_status":"EXPLORATORY_BENCHMARK",
        "limitations":[
            "Structured synthetic source is not natural-language source ingestion",
            "Python candidate-lens lookup and SQLite execution are not equivalent implementation stacks",
            "Graph semantics only; underlying source facts are unverified",
            "Index/source loading is included in totals; mutation maintenance is not measured",
            "Results vary by machine, cache, interpreter and selected workload",
            "No proof of novel grammar, permitted omissions, or domain completeness",
        ],
    }
    result["fingerprint"]=digest(result)
    return result

def simulate_update(source: dict, training: dict, contract: dict) -> dict:
    """Rebuild materializations after one new source edge, verify update equivalence.

    Unlike timing, this is a correctness test of invalidation and reconstruction.
    Does not reuse a stale compiled lens.
    """
    first,second,_=_contract(source,contract)
    updated={"schema":source["schema"],"facts":[dict(x) for x in source["facts"]]}
    existing_ids={f["id"] for f in updated["facts"]}
    ident="update-right"
    if ident in existing_ids:
        raise ValueError("Fixture update id already present")
    # Add one new second-edge to an existing intermediate node.
    mid=next(f["object"] for f in updated["facts"] if f["predicate"]==first)
    updated["facts"].append({"id":ident,"subject":mid,"predicate":second,
        "object":"updated-destination","source_ref":"update#1"})
    db=_db(updated)
    try:
        _sql_materialize(db,first,second)
        lens=_rct_materialize(training,updated,first,second)
        subjects={f["subject"] for f in updated["facts"]}
        ok=all(_sql_direct(db,s,first,second)
               ==_sql_materialized(db,s)==lens.get(s,[])
               for s in subjects)
        if not ok:
            raise AssertionError("Updated source results diverged")
        return {"status":"STRUCTURALLY_MATCHED","source_changed":True,
                "old_sha256":digest(source),"new_sha256":digest(updated),
                "recompiled":True,"qualityrag_admission":"INCONCLUSIVE"}
    finally:
        db.close()
