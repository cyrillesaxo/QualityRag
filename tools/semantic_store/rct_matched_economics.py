"""Matched-query economics for the bounded RCT mixed-operator grammar.

Compares exactly the same finite PATH(p,q) AND EDGE(r) relation with indexed
SQLite direct joins, materialized SQLite, and a Python purpose-lens lookup.
These implementations do NOT have equal governance capabilities or runtime
environments. Benchmark figures are local exploratory measurements only.
"""
from __future__ import annotations

import sqlite3
from statistics import median
from time import perf_counter_ns

from rct_grammar import _validate
from rct_operator_ast import _evaluate_relations
from rct_end_to_end import run_structural_pipeline
from store import digest

SCHEMA = "rct.matched-query-economics/v2"
BACKENDS = ("sql_direct","sql_materialized","rct_candidate")


def _predicates(ast: dict) -> tuple[str,str,str]:
    if not isinstance(ast, dict) or ast.get("op") != "AND":
        raise ValueError("Only mixed PATH/AND query workloads are comparable here")
    left,right = ast["left"],ast["right"]
    if left.get("op") == "EDGE":
        left,right = right,left
    if (left.get("op") != "PATH" or right.get("op") != "EDGE"
            or left["left"].get("op") != "EDGE"
            or left["right"].get("op") != "EDGE"):
        raise ValueError("SQL baseline for this operator shape is not implemented")
    return left["left"]["predicate"],left["right"]["predicate"],right["predicate"]


def _sql_data(source: dict):
    conn=sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE facts (id TEXT PRIMARY KEY, s TEXT, p TEXT, o TEXT)")
    conn.executemany("INSERT INTO facts VALUES (?,?,?,?)",
                     ((f["id"],f["subject"],f["predicate"],f["object"])
                      for f in _validate(source)))
    conn.execute("CREATE INDEX spo ON facts(s,p,o)")
    conn.execute("CREATE INDEX pso ON facts(p,s,o)")
    conn.commit()
    return conn


def _join_query(p: str, q: str, r: str, *, subject: bool) -> str:
    return ("""SELECT DISTINCT b.o FROM facts a
      JOIN facts b ON a.o=b.s
      JOIN facts c ON a.s=c.s AND b.o=c.o
      WHERE a.p=? AND b.p=? AND c.p=?""" +
      (" AND a.s=?" if subject else "") + " ORDER BY b.o")


def run_matched_economics(training: dict, training_labels: list[dict],
                         source: dict, labels: list[dict], grammar: dict,
                         *, purpose: str, required_predicates: list[str],
                         allowed_omission_predicates: list[str],
                         repetitions: int = 5, trials: int = 3) -> dict:
    if (type(repetitions) is not int or not 1 <= repetitions <= 100
            or type(trials) is not int or not 1 <= trials <= 10):
        raise ValueError("Bounded trial/repetition count required")
    facts=_validate(source)
    subjects=sorted(set(f["subject"] for f in facts))
    runs=[]
    for i in range(trials):
        started=perf_counter_ns()
        structural=run_structural_pipeline(
            training,training_labels,source,labels,grammar,
            purpose=purpose,lens_id="matched-economics",
            required_predicates=required_predicates,
            allowed_omission_predicates=allowed_omission_predicates)
        pipeline_ns=perf_counter_ns()-started
        if (structural["stage"] != "RESEARCH_CANDIDATE"
                or structural["conservation"]["finite_structural_verdict"] != "SAT"):
            raise ValueError("Candidate cannot be compared without finite conservation")
        ast=structural["grammar_candidate"]["ast"]
        p,q,r=_predicates(ast)
        start=perf_counter_ns()
        conn=_sql_data(source)
        sql_load_ns=perf_counter_ns()-start
        try:
            direct_query=_join_query(p,q,r,subject=True)
            start=perf_counter_ns()
            direct={}
            for _ in range(repetitions):
                for s in subjects:
                    direct[s]=tuple(row[0] for row in
                        conn.execute(direct_query,(p,q,r,s)).fetchall())
            direct_ns=perf_counter_ns()-start
            start=perf_counter_ns()
            conn.execute("CREATE TABLE derived (s TEXT, o TEXT)")
            conn.execute("""INSERT INTO derived SELECT DISTINCT a.s,b.o FROM facts a
                  JOIN facts b ON a.o=b.s
                  JOIN facts c ON a.s=c.s AND b.o=c.o
                  WHERE a.p=? AND b.p=? AND c.p=?""",(p,q,r))
            conn.execute("CREATE INDEX derived_so ON derived(s,o)")
            mat_build_ns=perf_counter_ns()-start
            start=perf_counter_ns()
            material={}
            for _ in range(repetitions):
                for s in subjects:
                    material[s]=tuple(row[0] for row in conn.execute(
                        "SELECT o FROM derived WHERE s=? ORDER BY o",(s,)).fetchall())
            mat_ns=perf_counter_ns()-start
            kept=set(structural["purpose_lens"]["selected_fact_ids"])
            started=perf_counter_ns()
            pairs=_evaluate_relations(
                [f for f in facts if f["id"] in kept],ast,[0])
            index={}
            for src,dst in pairs:
                index.setdefault(src,[]).append(dst)
            index={s:tuple(sorted(values)) for s,values in index.items()}
            candidate_build_ns=perf_counter_ns()-started
            start=perf_counter_ns()
            candidate={}
            for _ in range(repetitions):
                for s in subjects:
                    candidate[s]=index.get(s,())
            candidate_query_ns=perf_counter_ns()-start
            if direct!=material or direct!=candidate:
                raise AssertionError("Unequal finite workload answers: benchmark invalid")
            totals={
                "sql_direct":sql_load_ns+direct_ns,
                "sql_materialized":sql_load_ns+mat_build_ns+mat_ns,
                "rct_candidate":pipeline_ns+candidate_build_ns+candidate_query_ns,
            }
            runs.append({
                "trial":i+1,
                "timings_ns":{
                    "sql_source_ingest":sql_load_ns,
                    "sql_direct_query":direct_ns,
                    "sql_materialized_build":mat_build_ns,
                    "sql_materialized_query":mat_ns,
                    "rct_pipeline_including_induction_verification_and_reconstruction":pipeline_ns,
                    "rct_lens_materialization":candidate_build_ns,
                    "rct_query":candidate_query_ns,
                },
                "total_ns":totals,
                "verified_identical_query_answers":True,
                "canonical_reconstruction_bytes":
                    structural["reconstruction"]["frame"]["original_bytes"],
                "reference_compressed_bytes":
                    structural["reconstruction"]["frame"]["compressed_bytes"],
            })
        finally:
            conn.close()
    medians={backend:median(x["total_ns"][backend] for x in runs)
             for backend in BACKENDS}
    result={
        "schema":SCHEMA,
        "source_sha256":digest(source),"training_sha256":digest(training),
        "trials":runs,"median_total_ns":medians,
        "queries_per_backend":len(subjects)*repetitions,
        "matched_answer_equivalence":True,
        "economic_outcome":"EXPLORATORY_RUNTIME_DEPENDENT_NOT_ADMISSION",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "limitations":[
            "SQL baselines perform relational queries; RCT additionally creates and checks a purpose lens",
            "Python and SQLite implementation languages are not controlled for performance",
            "Full update/rebuild economics are exercised separately by v1.0",
            "Training data acquisition, signed governance and FF-RCT native execution are excluded",
            "The codec is a reversible reference frame, not the FF-RCT implementation",
            "No general performance advantage follows from these synthetic inputs",
        ],
    }
    result["fingerprint"]=digest(result)
    return result
