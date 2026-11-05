"""Bounded, proposal-driven grammar/activation co-evolution (research only).

This is not an LLM or autonomous scientific discovery. It does synthesize
variable-length composition candidates from training data, derives activation
strategies from workload frequencies, and evaluates paired source revisions
against independent SQLite relation-query oracles.

No outcome can bypass the canonical APX/QualityRag admission gate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from time import perf_counter_ns
import json
import sqlite3

from rct_grammar import _validate
from rct_reference_frame import encode_reference_frame, decode_reference_frame
from store import canonical_bytes, digest

SCHEMA = "rct.garden-coevolution/v0.1"
MAX_FACTS = 400
MAX_SUBJECTS = 120
MAX_PROPOSALS = 24
MAX_PATH_LENGTH = 4
ACTIVATIONS = ("ON_DEMAND", "FREQUENCY_AWARE", "ALL")
GRAMMARS = ("DIRECT_TRAVERSAL", "MATERIALIZED_COMPOSITION")
REGIME = "FINITE_TYPED_GRAPH_ONLY"


def _facts(source):
    facts = _validate(source)
    if len(facts) > MAX_FACTS:
        raise ValueError("Fact budget exceeded")
    return facts


def _outgoing(facts):
    outgoing = defaultdict(list)
    for fact in facts:
        outgoing[fact["subject"]].append(fact)
    return outgoing


def synthesize_operators(training: dict, *, max_path_length=3,
                         max_proposals=12, minimum_support=1) -> list[dict]:
    """Mine variable-length paths, not just a fixed two-hop predicate pair.

    Derived operators are candidate structural path programs. A path of
    length three was not available in the earlier two-hop-only experiment.
    """
    facts = _facts(training)
    if (type(max_path_length) is not int or not 2 <= max_path_length <= MAX_PATH_LENGTH or
        type(max_proposals) is not int or not 1 <= max_proposals <= MAX_PROPOSALS or
        type(minimum_support) is not int or not 1 <= minimum_support <= 100):
        raise ValueError("Invalid proposal search bounds")
    adjacency = _outgoing(facts)
    paths = defaultdict(set)
    for first in facts:
        stack = [(first["object"], (first["predicate"],), (first["id"],))]
        while stack:
            node, predicates, witnesses = stack.pop()
            if len(predicates) >= 2:
                paths[predicates].add(witnesses)
            if len(predicates) >= max_path_length:
                continue
            for edge in adjacency.get(node, ()):
                # A bounded walk may include a cycle; limit by path length.
                stack.append((edge["object"], (*predicates, edge["predicate"]),
                              (*witnesses, edge["id"])))
    candidates = []
    for predicates, witnesses in paths.items():
        if len(witnesses) < minimum_support:
            continue
        candidate = {
            "schema": "rct.garden-operator-proposal/v0.1",
            "type": "RELATION_PATH_COMPOSITION",
            "predicate_path": list(predicates),
            "support_fact_ids": sorted({fid for path in witnesses for fid in path}),
            "support_path_count": len(witnesses),
            "training_sha256": digest(training),
            "status": "UNVERIFIED_CANDIDATE",
            "semantics": REGIME,
            "qualityrag_admission": "INCONCLUSIVE",
            "promotion_authorized": False,
        }
        candidate["fingerprint"] = digest(candidate)
        candidates.append(candidate)
    return sorted(candidates, key=lambda c: (-c["support_path_count"],
                   -len(c["predicate_path"]), c["predicate_path"]))[:max_proposals]


def _reference_sql(facts, predicate_path, subjects):
    """Independent relational oracle through parameterized recursive CTE.

    Path length is bounded and predicate parameters are never interpolated
    into SQL. Uses UNION (not UNION ALL) for set semantics at every layer.
    """
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE f(s TEXT NOT NULL,p TEXT NOT NULL,o TEXT NOT NULL)")
        db.executemany("INSERT INTO f VALUES (?,?,?)",
                       [(f["subject"], f["predicate"], f["object"]) for f in facts])
        db.execute("CREATE INDEX idx_sp ON f(s,p)")
        # Count hops by expanding join clauses; no untrusted SQL identifiers.
        joins = []
        for i in range(len(predicate_path)):
            alias = f"t{i}"
            joins.append(
                f"JOIN f {alias} ON {alias}.s = " +
                ("?" if i == 0 else f"t{i-1}.o") +
                f" AND {alias}.p = ?")
        statement = "SELECT DISTINCT t" + str(len(predicate_path) - 1) + ".o FROM (SELECT 1) anchor " + " ".join(joins)
        result = {}
        for subject in subjects:
            params = [subject, predicate_path[0]]
            params += list(predicate_path[1:])
            result[subject] = tuple(sorted(row[0] for row in db.execute(statement, params)))
        return result
    finally:
        db.close()


def _execute_path(adjacency, path, subject):
    frontier = {subject}
    for predicate in path:
        next_nodes = set()
        for node in frontier:
            for fact in adjacency.get(node, ()):
                if fact["predicate"] == predicate:
                    next_nodes.add(fact["object"])
        frontier = next_nodes
        if not frontier:
            break
    return tuple(sorted(frontier))


def _activation_proposals(workload, valid_subjects):
    """Compile activation signals, including workload-frequency-derived hot set."""
    counts = Counter(workload["subjects"])
    # A reviewed workload plan explicitly indicates which subjects may be
    # prefetched. High-frequency subjects are computed, not hard-coded.
    max_hot = max(1, min(len(counts), (len(counts) + 1) // 2))
    hot = [s for s, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:max_hot]]
    return [
        {"policy": "ON_DEMAND", "prefetch_subjects": []},
        {"policy": "FREQUENCY_AWARE", "prefetch_subjects": hot},
        {"policy": "ALL", "prefetch_subjects": sorted(valid_subjects)},
    ]


def _phase(source, path, workload, activation, grammar):
    facts = _facts(source)
    all_subjects = sorted(set(f["subject"] for f in facts) | set(f["object"] for f in facts))
    if len(all_subjects) > MAX_SUBJECTS:
        raise ValueError("Too many verifier subjects")
    start = perf_counter_ns()
    frame = encode_reference_frame(source)
    decoded = decode_reference_frame(frame)
    if digest(decoded) != digest(source):
        raise ValueError("Exact reconstruction failed")
    codec_ns = perf_counter_ns() - start
    start = perf_counter_ns()
    gold = _reference_sql(facts, path, all_subjects)
    oracle_ns = perf_counter_ns() - start
    start = perf_counter_ns()
    adjacency = _outgoing(facts)
    if grammar == "DIRECT_TRAVERSAL":
        representation = adjacency
        def lookup(subject):
            return _execute_path(representation, path, subject)
    elif grammar == "MATERIALIZED_COMPOSITION":
        representation = {subject: _execute_path(adjacency, path, subject)
                          for subject in all_subjects}
        def lookup(subject):
            return representation.get(subject, ())
    else:
        raise ValueError("Unknown representation grammar")
    build_ns = perf_counter_ns() - start
    cache = {}
    start = perf_counter_ns()
    for subject in activation["prefetch_subjects"]:
        cache[subject] = lookup(subject)
    activation_ns = perf_counter_ns() - start
    start = perf_counter_ns()
    produced = {}
    for subject in workload["subjects"]:
        if subject not in cache:
            cache[subject] = lookup(subject)
        produced[subject] = cache[subject]
    lookup_ns = perf_counter_ns() - start
    start = perf_counter_ns()
    mismatches = [
        subject for subject in all_subjects
        if lookup(subject) != gold[subject]
    ]
    verifier_ns = perf_counter_ns() - start
    if mismatches or any(produced[s] != gold[s] for s in produced):
        raise ValueError("Finite source/target relation mismatch")
    active_representation = (
        {k: [[x["id"], x["predicate"], x["object"]] for x in edges]
         for k, edges in sorted(representation.items())}
        if grammar == "DIRECT_TRAVERSAL"
        else {k: list(v) for k, v in sorted(representation.items())}
    )
    active_bytes = len(canonical_bytes({
        "grammar": grammar, "representation": active_representation,
        "cache": cache,
    }))
    return {
        "source_sha256": digest(source),
        "frame_fingerprint": frame["fingerprint"],
        "result_sha256": digest({s: list(produced[s]) for s in sorted(produced)}),
        "covered_subjects": len(all_subjects),
        "exact_reconstruction": True,
        "finite_structural_verdict": "SAT",
        "activation_signals": {
            "predicate_path": path,
            "prefetch_subjects": activation["prefetch_subjects"],
            "source_sha256": digest(source),
        },
        "cost_ns": {
            "codec_reconstruction": codec_ns, "independent_sql_oracle": oracle_ns,
            "representation_build": build_ns, "activation": activation_ns,
            "query": lookup_ns, "verification": verifier_ns,
        },
        "total_ns": codec_ns + oracle_ns + build_ns + activation_ns + lookup_ns + verifier_ns,
        "serialized_bytes": len(canonical_bytes(frame)) + active_bytes,
        "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
    }


def run_research_cycle(training, source, revised_source, workload, *,
                       trials=2, max_proposals=12):
    """Synthesize grammar paths and co-evaluate derived activation signals.

    This is an explicit, synchronous bounded cycle. It is not a daemon and
    does not automatically learn, promote, or invoke generative AI models.
    """
    _facts(training)
    current = _facts(source)
    changed = _facts(revised_source)
    if digest(training) in (digest(source), digest(revised_source)):
        raise ValueError("Train/eval contamination: identical source")
    if digest(source) == digest(revised_source):
        raise ValueError("Revision must change source")
    if not isinstance(workload, dict):
        raise ValueError("Workload required")
    subjects = workload.get("subjects")
    if (not isinstance(subjects, list) or not 1 <= len(subjects) <= MAX_SUBJECTS or
        any(not isinstance(x, str) or not x for x in subjects) or
        type(trials) is not int or not 2 <= trials <= 8):
        raise ValueError("Invalid research workload")
    # Supplying an exact path is a held-out evaluation selector; the operator
    # still has to be synthesized from training data, not from validation.
    desired = workload.get("predicate_path")
    if not isinstance(desired, list) or not 2 <= len(desired) <= MAX_PATH_LENGTH or any(
        not isinstance(p, str) or not p for p in desired):
        raise ValueError("Typed predicate path required")
    if type(max_proposals) is not int or not 1 <= max_proposals <= MAX_PROPOSALS:
        raise ValueError("Invalid proposal limit")
    candidates = synthesize_operators(training, max_path_length=MAX_PATH_LENGTH,
                                       max_proposals=max_proposals)
    candidate = next((c for c in candidates if c["predicate_path"] == desired), None)
    if candidate is None:
        return {
            "schema": SCHEMA, "status": "UNKNOWN",
            "reason": "NO_TRAINED_GRAMMAR_FOR_WORKLOAD",
            "training_sha256": digest(training), "candidate_count": len(candidates),
            "qualityrag_admission": "INCONCLUSIVE", "promotion_authorized": False,
            "can_generate": False,
        }
    all_subjects = sorted({f["subject"] for f in current + changed} |
                          {f["object"] for f in current + changed})
    if len(all_subjects) > MAX_SUBJECTS:
        raise ValueError("Too many evaluation subjects")
    activation_options = _activation_proposals(workload, all_subjects)
    results = []
    for grammar in GRAMMARS:
        for activation in activation_options:
            measurements = []
            for _ in range(trials):
                before = _phase(source, desired, workload, activation, grammar)
                after = _phase(revised_source, desired, workload, activation, grammar)
                measurements.append({
                    "before": before, "after": after,
                    "total_ns": before["total_ns"] + after["total_ns"],
                    "peak_serialized_bytes": max(before["serialized_bytes"],
                                                 after["serialized_bytes"]),
                })
            results.append({
                "operator_fingerprint": candidate["fingerprint"],
                "operator_predicate_path": desired,
                "grammar": grammar,
                "activation": activation,
                "median_total_ns": median(x["total_ns"] for x in measurements),
                "median_peak_serialized_bytes": median(x["peak_serialized_bytes"]
                                                        for x in measurements),
                "measurements": measurements,
                "status": "EXPERIMENTAL_CANDIDATE",
                "qualityrag_admission": "INCONCLUSIVE",
                "promotion_authorized": False,
            })
    nondominated = []
    for i, result in enumerate(results):
        if not any(
            other is not result and
            other["median_total_ns"] <= result["median_total_ns"] and
            other["median_peak_serialized_bytes"] <= result["median_peak_serialized_bytes"] and
            (other["median_total_ns"] < result["median_total_ns"] or
             other["median_peak_serialized_bytes"] < result["median_peak_serialized_bytes"])
            for other in results
        ):
            nondominated.append(i)
    output = {
        "schema": SCHEMA, "status": "CANDIDATES_EVALUATED",
        "training_sha256": digest(training), "source_sha256": digest(source),
        "revised_sha256": digest(revised_source), "workload_sha256": digest(workload),
        "generated_operators": candidates,
        "evaluated_operator": candidate,
        "results": results, "pareto_candidate_indices": nondominated,
        "champion": None, "promotion_authorized": False,
        "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
        "counterexamples": [],
        "limitations": [
            "Candidate novelty means variable-length path synthesis within a predefined composition family.",
            "Operator path selected by researcher; autonomous operator proposal and orchestration absent.",
            "No native FF-RCT, authenticated PackSpec, D15, TERM or canonical k/b/c/tau admission.",
            "Small finite graphs and serialized memory proxies do not establish workload superiority.",
            "SQL oracle work is included in total cost; no production-class SQL baseline yet.",
            "Source revisions are supplied explicitly; no continuous background monitor.",
        ],
    }
    output["fingerprint"] = digest(output)
    return output



def _discriminating_probes(graph, candidates, examples, *, limit=8):
    """Find unlabeled training queries whose candidate predictions disagree.

    This proposes experiments, never fabricates an answer. If no training
    example distinguishes the surviving operators, new-regime evidence is
    required instead of arbitrary tie-breaking.
    """
    seen = {(item["subject"], item["destination"]) for item in examples}
    nodes = sorted(set(f["subject"] for f in graph) | set(f["object"] for f in graph))
    adjacency = _outgoing(graph)
    probes = []
    for subject in nodes:
        reachable = [
            set(_execute_path(adjacency, candidate["predicate_path"], subject))
            for candidate in candidates]
        if not reachable:
            continue
        targets = sorted(set().union(*reachable))
        for target in targets:
            if (subject, target) in seen:
                continue
            votes = [target in xs for xs in reachable]
            if len(set(votes)) < 2:
                continue
            probes.append({
                "subject": subject, "destination": target,
                "hypothesis_predictions": [
                    {"predicate_path": candidate["predicate_path"], "predicts": vote}
                    for candidate, vote in zip(candidates, votes)],
                "reference_answer": "UNOBSERVED",
                "status": "DISCRIMINATING_PROBE_PROPOSED",
            })
            if len(probes) >= limit:
                return probes
    return probes


def induce_from_examples(training: dict, examples: list[dict], *,
                         max_proposals=24) -> dict:
    """Select a grammar path using labelled *training* examples only.

    When multiple different operators explain all observations, the
    hypothesis is ambiguous and needs a discriminating probe. A successful
    label fit is not a semantic proof or permission to promote an operator.
    """
    facts = _facts(training)
    if not isinstance(examples, list) or not 2 <= len(examples) <= 100:
        raise ValueError("Bounded labelled examples required")
    known_nodes = {f["subject"] for f in facts} | {f["object"] for f in facts}
    positive = 0
    negative = 0
    for item in examples:
        if (not isinstance(item, dict) or
            not isinstance(item.get("subject"), str) or
            not isinstance(item.get("destination"), str) or
            type(item.get("expected")) is not bool or
            item["subject"] not in known_nodes or
            item["destination"] not in known_nodes):
            raise ValueError("Examples must refer only to training nodes")
        positive += int(item["expected"])
        negative += int(not item["expected"])
    if not positive or not negative:
        raise ValueError("Both positive and adversarial negative examples required")
    candidates = synthesize_operators(training, max_path_length=MAX_PATH_LENGTH,
                                       max_proposals=max_proposals)
    graph = _outgoing(facts)
    evaluations = []
    for operator in candidates:
        predictions = [
            item["destination"] in _execute_path(graph, operator["predicate_path"],
                                                  item["subject"])
            for item in examples]
        errors = [
            {"example_index": i, "expected": example["expected"],
             "actual": predictions[i]}
            for i, example in enumerate(examples)
            if predictions[i] != example["expected"]]
        evaluations.append({
            "operator_fingerprint": operator["fingerprint"],
            "predicate_path": operator["predicate_path"],
            "error_count": len(errors), "counterexamples": errors,
        })
    winners = [row for row in evaluations if row["error_count"] == 0]
    outcome = ("UNIQUE_TRAINING_HYPOTHESIS" if len(winners) == 1
               else "AMBIGUOUS" if winners else "UNRESOLVED")
    competing = [c for c in candidates if c["fingerprint"] in
                 {row["operator_fingerprint"] for row in winners}]
    probes = (_discriminating_probes(facts, competing, examples)
              if outcome == "AMBIGUOUS" else [])
    return {
        "schema": "rct.garden-hypothesis/v0.1", "status": outcome,
        "training_sha256": digest(training),
        "examples_sha256": digest(examples),
        "selected_predicate_path": winners[0]["predicate_path"] if len(winners) == 1 else None,
        "matched_candidate_count": len(winners),
        "discriminating_probes": probes,
        "probe_limitation": (
            "INSUFFICIENT_CURRENT_REGIME_DIVERGENCE"
            if outcome == "AMBIGUOUS" and not probes else None),
        "evaluations": evaluations,
        "qualityrag_admission": "INCONCLUSIVE", "promotion_authorized": False,
        "next_step": "HELDOUT_EVALUATION" if len(winners) == 1
                     else "GENERATE_DISCRIMINATING_PROBE",
    }


def run_investigation(training, examples, source, revised_source, workload, *,
                      trials=2, max_proposals=24):
    """Train-only hypothesis discovery followed by frozen held-out evaluation."""
    hypothesis = induce_from_examples(training, examples,
                                      max_proposals=max_proposals)
    if hypothesis["status"] != "UNIQUE_TRAINING_HYPOTHESIS":
        return {
            "schema": "rct.garden-investigation/v0.1",
            "status": hypothesis["status"], "hypothesis": hypothesis,
            "experiment": None, "qualityrag_admission": "INCONCLUSIVE",
            "can_generate": False, "promotion_authorized": False,
        }
    if not isinstance(workload, dict) or "predicate_path" in workload:
        raise ValueError("Investigation workload must not disclose the selected operator")
    derived_workload = dict(workload)
    derived_workload["predicate_path"] = hypothesis["selected_predicate_path"]
    experiment = run_research_cycle(
        training, source, revised_source, derived_workload,
        trials=trials, max_proposals=max_proposals)
    return {
        "schema": "rct.garden-investigation/v0.1",
        "status": experiment["status"], "hypothesis": hypothesis,
        "experiment": experiment,
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False, "promotion_authorized": False,
    }
