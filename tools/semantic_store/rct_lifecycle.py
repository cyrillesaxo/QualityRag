"""Lifecycle workload comparison and cross-topology transfer for RCT v1.0.

Experimental structural semantics only. This is not a PackSpec verifier or a
comparison of equal implementation languages. Candidate grammars are preexisting
two-hop composition templates mined over training facts.
"""
from __future__ import annotations

from statistics import median
from time import perf_counter_ns

from rct_benchmark import (
    _contract, _db, _measure, _rct_materialize, _run_queries,
    _sql_direct, _sql_materialize, _sql_materialized, make_contract,
)
from rct_grammar import _validate
from store import digest

SCHEMA = "rct.lifecycle-economics/v1.0"
BACKENDS = ("direct_sql", "materialized_sql", "candidate_lens")


def make_cross_topology_fixture(*, entity_count: int = 48, prefix: str = "cross-") -> dict:
    """Create a branching graph with fan-out, multiple endpoints and distractors.

    Unlike the v0.9 fixture, intermediary nodes branch to two destinations,
    some entities have two intermediary links, and extra unrelated edges exist.
    Predicate names are deliberately unchanged, so the proposed rule transfers.
    """
    if type(entity_count) is not int or not 8 <= entity_count <= 200:
        raise ValueError("entity_count must be between 8 and 200")
    facts = []
    for i in range(entity_count):
        entity = f"{prefix}entity-{i}"
        middle = f"{prefix}hub-{i % 7}"
        facts.append({"id": f"{prefix}left-{i}", "subject": entity,
                      "predicate": "projects_to", "object": middle,
                      "source_ref": f"branch#{i}"})
        if i % 5 == 0:
            facts.append({"id": f"{prefix}second-{i}", "subject": entity,
                          "predicate": "projects_to",
                          "object": f"{prefix}hub-{(i + 2) % 7}",
                          "source_ref": f"branch#{i}"})
        facts.append({"id": f"{prefix}distractor-{i}", "subject": entity,
                      "predicate": "adjacent_to",
                      "object": f"{prefix}noise-{i}",
                      "source_ref": f"noise#{i}"})
    for hub in range(7):
        for dest in range(2):
            facts.append({"id": f"{prefix}right-{hub}-{dest}",
                          "subject": f"{prefix}hub-{hub}",
                          "predicate": "belongs_to",
                          "object": f"{prefix}domain-{(hub + dest) % 4}",
                          "source_ref": f"branch#hub-{hub}"})
    return {"schema": "rct.structured-ast/v1", "facts": facts}


def _updated_source(source: dict, first: str, second: str) -> tuple[dict, dict]:
    facts = _validate(source)
    changed = {"schema": source["schema"], "facts": [dict(f) for f in facts]}
    ids = {f["id"] for f in facts}
    candidate_id = "lifecycle-add-second-edge"
    if candidate_id in ids:
        raise ValueError("Update id collision")
    first_edge = next((f for f in facts if f["predicate"] == first), None)
    if first_edge is None:
        raise ValueError("No first-hop edge for update")
    new_fact = {"id": candidate_id, "subject": first_edge["object"],
                "predicate": second, "object": "lifecycle-new-destination",
                "source_ref": "update#1"}
    changed["facts"].append(new_fact)
    return changed, new_fact


def _measure_query_set(db, lens, subjects, repetitions, first, second):
    direct, direct_ns = _measure(
        lambda: _run_queries(lambda s: _sql_direct(db, s, first, second),
                             subjects, repetitions))
    materialized, materialized_ns = _measure(
        lambda: _run_queries(lambda s: _sql_materialized(db, s),
                             subjects, repetitions))
    candidate, lens_ns = _measure(
        lambda: _run_queries(lambda s: lens.get(s, []),
                             subjects, repetitions))
    if direct != materialized or direct != candidate:
        raise AssertionError("Answer mismatch: lifecycle benchmark invalid")
    return {"direct_sql": direct_ns, "materialized_sql": materialized_ns,
            "candidate_lens": lens_ns, "result_sha256": direct[0]}


def run_lifecycle(training: dict, source: dict, contract: dict,
                  *, trials: int = 3) -> dict:
    """Measure create/query/update/rebuild/query using the same queries.

    Measures full SQL view reconstruction rather than incremental SQL maintenance.
    Does not account for the cost of constructing or verifying the training set.
    """
    _validate(training)
    _validate(source)
    first, second, repetitions = _contract(source, contract)
    if type(trials) is not int or not 1 <= trials <= 12:
        raise ValueError("Invalid number of trials")
    if digest(training) == digest(source):
        raise ValueError("Training and evaluation sources must differ")
    updated, new_fact = _updated_source(source, first, second)
    subjects = sorted({f["subject"] for f in updated["facts"]})
    records = []
    for index in range(trials):
        db, load_ns = _measure(lambda: _db(source))
        try:
            _, sql_creation_ns = _measure(lambda: _sql_materialize(db, first, second))
            lens, lens_creation_ns = _measure(
                lambda: _rct_materialize(training, source, first, second))
            phase0 = _measure_query_set(db, lens, subjects, repetitions, first, second)

            _, insertion_ns = _measure(
                lambda: db.execute(
                    "INSERT INTO facts VALUES (?,?,?,?)",
                    (new_fact["id"], new_fact["subject"],
                     new_fact["predicate"], new_fact["object"])))
            _, sql_rebuild_ns = _measure(lambda: _sql_materialize(db, first, second))
            updated_lens, lens_rebuild_ns = _measure(
                lambda: _rct_materialize(training, updated, first, second))
            phase1 = _measure_query_set(
                db, updated_lens, subjects, repetitions, first, second)
            if phase0["result_sha256"] == phase1["result_sha256"]:
                raise AssertionError("Update failed to change the workload answers")

            items = {}
            for backend in BACKENDS:
                build = (sql_creation_ns + sql_rebuild_ns
                         if backend == "materialized_sql" else
                         lens_creation_ns + lens_rebuild_ns
                         if backend == "candidate_lens" else 0)
                queries = phase0[backend] + phase1[backend]
                items[backend] = {
                    "build_and_rebuild_ns": build, "query_ns": queries,
                    "shared_source_load_and_update_ns": load_ns + insertion_ns,
                    "total_ns": load_ns + insertion_ns + build + queries}
            records.append({
                "trial": index + 1, "backend_costs": items,
                "before_output_sha256": phase0["result_sha256"],
                "after_output_sha256": phase1["result_sha256"],
                "same_answers_across_backends": True,
                "source_mutation_changed_answers": True,
            })
        finally:
            db.close()

    median_costs = {
        backend: {field: median(record["backend_costs"][backend][field]
                                for record in records)
                  for field in ("build_and_rebuild_ns", "query_ns",
                                "shared_source_load_and_update_ns", "total_ns")}
        for backend in BACKENDS}
    best_sql = min(median_costs["direct_sql"]["total_ns"],
                   median_costs["materialized_sql"]["total_ns"])
    lens_total = median_costs["candidate_lens"]["total_ns"]
    # Winner is strictly measured on this synthetic workload, not a product claim.
    comparative_verdict = ("CANDIDATE_LENS_LOWER_MEASURED_TOTAL"
                           if lens_total < best_sql else
                           "SQL_BASELINE_EQUAL_OR_LOWER_MEASURED_TOTAL")

    result = {
        "schema": SCHEMA,
        "source_sha256": digest(source),
        "updated_source_sha256": digest(updated),
        "training_source_sha256": digest(training),
        "workload_contract_sha256": digest(contract),
        "topology": "SUPPLIED",
        "fact_count_before": len(source["facts"]),
        "fact_count_after": len(updated["facts"]),
        "queries_per_phase": len(subjects) * repetitions,
        "trials": records,
        "median_ns": median_costs,
        "comparative_verdict": comparative_verdict,
        "strongest_sql_total_ns": best_sql,
        "identical_answers": True,
        "mutation_changed_answers": True,
        "qualityrag_admission": "INCONCLUSIVE",
        "packspec_verified": False,
        "limitations": [
            "Experimental contract is not an authenticated PackSpec",
            "Synthetic typed graphs and finite structural query semantics only",
            "Two-hop operator template remains predefined",
            "Full-rebuild SQL baseline; incremental SQL maintenance not included",
            "Language/runtime differences bias absolute comparisons",
            "Training dataset construction and verification costs excluded",
            "Source authenticity and higher-level semantic correctness unverified",
            "No measured memory, storage or FF-RCT reconstruction costs",
        ]}
    result["fingerprint"] = digest(result)
    return result


def run_cross_topology_suite(*, trials: int = 2,
                             repetitions: int = 4) -> dict:
    """Use a shared learned rule across two graph topologies, then measure both."""
    from rct_benchmark import make_fixture
    training = make_fixture(entities=32, prefix="train-")
    chain = make_fixture(entities=48, prefix="chain-")
    branch = make_cross_topology_fixture(entity_count=48, prefix="branch-")
    cases = {}
    for name, source in (("chain", chain), ("branch", branch)):
        contract = make_contract(source, repetitions=repetitions)
        cases[name] = run_lifecycle(training, source, contract, trials=trials)
    result = {
        "schema": "rct.topology-transfer/v1.0",
        "training_source_sha256": digest(training),
        "topologies": cases,
        "cross_topology_structural_equivalence": all(
            case["identical_answers"] for case in cases.values()),
        "qualityrag_admission": "INCONCLUSIVE",
        "transfer_scope": "SAME_PREDICATE_PAIR_DIFFERENT_GRAPH_TOPOLOGY",
        "limitation": "This is generalization of a known two-hop operator, not autonomous grammar invention"}
    result["fingerprint"] = digest(result)
    return result
