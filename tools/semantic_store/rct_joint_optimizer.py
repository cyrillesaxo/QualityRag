"""Joint grammar/activation research search for finite typed fact graphs.

A bounded, measurable *candidate* experiment. This is neither native FF-RCT
nor autonomous grammar invention nor QualityRag admission.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from time import perf_counter_ns
import json
import sqlite3

from rct_grammar import _validate
from rct_reference_frame import encode_reference_frame, decode_reference_frame
from rct_synthesis import propose_compositions
from store import canonical_bytes, digest

SCHEMA = "rct.joint-grammar-activation/v0.1"
GRAMMARS = ("DIRECT_FACT_GRAPH", "COMPOSE_TWO_HOP")
ACTIVATIONS = ("LAZY", "EAGER_WORKLOAD", "EAGER_ALL")
MAX_FACTS = 300
MAX_SUBJECTS = 100
MAX_CANDIDATES = 6


def _checked_source(source):
    facts = _validate(source)
    if len(facts) > MAX_FACTS:
        raise ValueError("Fact budget exceeded")
    return facts


def _sql_oracle(facts, first, second, subjects):
    """Independent SQL reference for *every* subject, including unqueried ones."""
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE TABLE fact(s TEXT, p TEXT, o TEXT)")
        con.executemany("INSERT INTO fact VALUES (?,?,?)",
                        ((f["subject"], f["predicate"], f["object"]) for f in facts))
        sql = """SELECT DISTINCT b.o FROM fact a JOIN fact b ON a.o=b.s
                 WHERE a.s=? AND a.p=? AND b.p=? ORDER BY b.o"""
        return {s: tuple(row[0] for row in con.execute(sql, (s, first, second)))
                for s in subjects}
    finally:
        con.close()


def _direct_index(facts):
    index = defaultdict(list)
    for fact in facts:
        index[fact["subject"]].append(fact)
    return index


def _direct_query(index, subject, pair):
    first, second = pair
    return tuple(sorted({
        right["object"]
        for left in index.get(subject, ())
        if left["predicate"] == first
        for right in index.get(left["object"], ())
        if right["predicate"] == second
    }))


def _composed_index(facts, pair):
    first, second = pair
    direct = _direct_index(facts)
    result = defaultdict(set)
    for fact in facts:
        if fact["predicate"] != first:
            continue
        for right in direct.get(fact["object"], ()):
            if right["predicate"] == second:
                result[fact["subject"]].add(right["object"])
    return {subject: tuple(sorted(dest)) for subject, dest in result.items()}


def _representation(facts, grammar, pair):
    if grammar == "DIRECT_FACT_GRAPH":
        return _direct_index(facts)
    return _composed_index(facts, pair)


def _lookup(rep, grammar, subject, pair):
    if grammar == "DIRECT_FACT_GRAPH":
        return _direct_query(rep, subject, pair)
    return rep.get(subject, ())


def _measured_phase(source, pair, subjects, repetitions, grammar, activation):
    facts = _checked_source(source)
    # Full-fidelity source is retained even when the active representation
    # omits non-workload predicates. The reference frame is NOT native FF-RCT.
    stamp = perf_counter_ns()
    frame = encode_reference_frame(source)
    restored = decode_reference_frame(frame)
    if digest(restored) != digest(source):
        raise AssertionError("Source reconstruction changed")
    reconstruction_ns = perf_counter_ns() - stamp
    all_subjects = sorted({f["subject"] for f in facts} | {f["object"] for f in facts})
    if len(all_subjects) > MAX_SUBJECTS:
        raise ValueError("Verification-subject budget exceeded")
    stamp = perf_counter_ns()
    oracle = _sql_oracle(facts, pair[0], pair[1], all_subjects)
    oracle_ns = perf_counter_ns() - stamp
    stamp = perf_counter_ns()
    representation = _representation(facts, grammar, pair)
    build_ns = perf_counter_ns() - stamp
    # Activation selectors determine what is actually materialized, not merely
    # which labels appear in a prompt. The cache is source-version-local.
    cache = {}
    stamp = perf_counter_ns()
    if activation == "EAGER_ALL":
        for subject in all_subjects:
            cache[subject] = _lookup(representation, grammar, subject, pair)
    elif activation == "EAGER_WORKLOAD":
        for subject in sorted(set(subjects)):
            cache[subject] = _lookup(representation, grammar, subject, pair)
    activation_ns = perf_counter_ns() - stamp
    stamp = perf_counter_ns()
    outputs = {}
    for _ in range(repetitions):
        for subject in subjects:
            if subject not in cache:
                cache[subject] = _lookup(representation, grammar, subject, pair)
            outputs[subject] = cache[subject]
    query_ns = perf_counter_ns() - stamp
    stamp = perf_counter_ns()
    # Verify EVERY feasible node, not only the activated workload; this is
    # finite structural correctness, not evidence authenticity or PackSpec.
    for subject in all_subjects:
        if _lookup(representation, grammar, subject, pair) != oracle[subject]:
            raise ValueError("Finite structural mismatch")
    if any(outputs[s] != oracle[s] for s in subjects):
        raise ValueError("Activated query mismatch")
    validation_ns = perf_counter_ns() - stamp
    # Measure actual serialized active index bytes rather than an arbitrary
    # "compression ratio" proxy. Full reference frame retained by all arms.
    index_for_size = (
        {k: [[f["id"], f["predicate"], f["object"]] for f in v]
         for k, v in representation.items()}
        if grammar == "DIRECT_FACT_GRAPH" else representation
    )
    active_bytes = len(canonical_bytes(index_for_size)) + len(canonical_bytes(cache))
    source_bytes = len(canonical_bytes(frame))
    return {
        "source_sha256": digest(source), "frame_fingerprint": frame["fingerprint"],
        "verified_all_subjects": len(all_subjects),
        "answers_sha256": digest({k: list(v) for k, v in sorted(outputs.items())}),
        "exact_reconstruction": True, "finite_answer_equivalence": True,
        "activation_signals": {
            "predicate_pair": list(pair), "subjects": list(subjects),
            "source_sha256": digest(source),
        },
        "resource_bytes": {"source_reference_frame": source_bytes,
                           "active_index_and_cache": active_bytes,
                           "total": source_bytes + active_bytes},
        "times_ns": {"reconstruction": reconstruction_ns,
                     "independent_sql_verification": oracle_ns,
                     "grammar_materialization": build_ns,
                     "activation": activation_ns,
                     "queries": query_ns,
                     "structural_validation": validation_ns},
        "total_ns": sum((reconstruction_ns, oracle_ns, build_ns,
                         activation_ns, query_ns, validation_ns)),
        "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
    }


def evaluate_joint_search(training, source, updated_source, workload, *, trials=3):
    """Compare 2 grammar families x 3 activation policies on a frozen workload.

    Updated source is a separately versioned snapshot; each policy must pay
    the reconstruction/rebuild cost again. Only sampled, finite measurements
    are ranked; no policy is certified or promoted.
    """
    train = _checked_source(training)
    _checked_source(source)
    _checked_source(updated_source)
    if digest(training) in (digest(source), digest(updated_source)):
        raise ValueError("Training and evaluation source must differ")
    if digest(source) == digest(updated_source):
        raise ValueError("Update did not change source")
    if not isinstance(workload, dict):
        raise ValueError("Workload required")
    pair = workload.get("predicate_pair")
    subjects = workload.get("subjects")
    repetitions = workload.get("repetitions")
    if (not isinstance(pair, list) or len(pair) != 2 or
        any(not isinstance(x, str) or not x for x in pair) or
        not isinstance(subjects, list) or not 1 <= len(subjects) <= MAX_SUBJECTS or
        any(not isinstance(x, str) or not x for x in subjects) or
        type(repetitions) is not int or not 1 <= repetitions <= 100 or
        type(trials) is not int or not 2 <= trials <= 10):
        raise ValueError("Invalid workload or trial limits")
    # The candidate composition rule must genuinely occur in independent
    # training data, otherwise it is not eligible for transfer.
    trained = propose_compositions(training, max_candidates=256,
                                   minimum_distinct_pairs=1)
    allowed = any(c["predicate_sequence"] == pair for c in trained)
    if not allowed:
        raise ValueError("No trained composition for requested predicate pair")
    results = []
    for grammar in GRAMMARS:
        for activation in ACTIVATIONS:
            measurements = []
            for _ in range(trials):
                before = _measured_phase(source, pair, subjects, repetitions,
                                         grammar, activation)
                after = _measured_phase(updated_source, pair, subjects, repetitions,
                                        grammar, activation)
                measurements.append({"before": before, "after": after,
                                     "total_ns": before["total_ns"] + after["total_ns"],
                                     "peak_bytes": max(before["resource_bytes"]["total"],
                                                       after["resource_bytes"]["total"])})
            results.append({
                "grammar": grammar, "activation": activation,
                "trials": measurements,
                "median_total_ns": median(m["total_ns"] for m in measurements),
                "median_peak_bytes": median(m["peak_bytes"] for m in measurements),
                "finite_structural_verdict": "SAT",
                "qualityrag_admission": "INCONCLUSIVE",
                "can_generate": False,
            })
    # A Pareto frontier is preferable to pretending one policy is best for
    # all storage, query, update and activation regimes.
    nondominated = []
    for r in results:
        dominated = any(
            (s["median_total_ns"] <= r["median_total_ns"] and
             s["median_peak_bytes"] <= r["median_peak_bytes"] and
             (s["median_total_ns"] < r["median_total_ns"] or
              s["median_peak_bytes"] < r["median_peak_bytes"]))
            for s in results if s is not r)
        if not dominated:
            nondominated.append({"grammar": r["grammar"], "activation": r["activation"]})
    receipt = {
        "schema": SCHEMA,
        "training_sha256": digest(training),
        "source_sha256": digest(source),
        "updated_source_sha256": digest(updated_source),
        "workload_sha256": digest(workload),
        "trained_composition": list(pair), "trials": trials,
        "results": results, "pareto_candidates": nondominated,
        "champion": None, "promotion_authorized": False,
        "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
        "interpretation": "FINITE_TYPED_GRAPH_RESEARCH_ONLY",
        "limitations": [
            "Grammar alternatives are preprogrammed direct facts and trained two-hop composition.",
            "Activation alternatives are preprogrammed lazy, workload-eager, and global-eager policies.",
            "This is joint candidate selection, not autonomous invention or live workload adaptation.",
            "Reference frame uses zlib, NOT native FF-RCT.",
            "Witness origin and PackSpec authority are not authenticated; D15/CUS/TERM not certified.",
            "Python implementation and SQL oracle have different runtime costs.",
            "Memory values are serialized proxies, not resident memory or actual disk allocation.",
            "Only two supplied snapshots are measured; no autonomous update monitoring.",
            "No production champion without approved evidence, independent verification and held-out workloads.",
        ],
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt
