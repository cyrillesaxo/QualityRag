"""Bounded Semantic Garden investigation controller.

The controller makes local next-action decisions: induce -> ask an external
oracle to resolve a discriminating probe -> re-induce -> evaluate six
grammar/activation candidates. It DOES NOT schedule itself, invent arbitrary
operator families, authenticate witnesses, run an LLM, or authorize admission.

An independent source of labels is mandatory for progress through ambiguity.
The reference oracle must NOT be the candidate path executor under test.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Callable

from rct_garden_coevolution import induce_from_examples, run_investigation
from store import digest

SCHEMA = "rct.garden-controller/v0.1"
PROBE_SCHEMA = "rct.external-probe-observation/v0.1"
MAX_PROBES = 6
MAX_EXAMPLES = 100


def _report(status, *, training, initial_examples, observed, events,
            investigation=None, remaining_budget=0):
    """Provenance-preserving research receipt: never an admission."""
    value = {
        "schema": SCHEMA, "status": status, "training_sha256": digest(training),
        "initial_examples_sha256": digest(initial_examples),
        "observations_sha256": digest(observed),
        "events": events, "external_probe_count": len(observed) - len(initial_examples),
        "remaining_probe_budget": remaining_budget,
        "investigation": investigation,
        "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
        "promotion_authorized": False,
        "limitations": [
            "Probe observations are supplied by an external callback and are not independently attested.",
            "The controller selects a path within a predeclared composition grammar; it does not invent operator families.",
            "No authenticated PackSpec, canonical D15/FFI/FF-RCT, or k/b/c/tau admission.",
            "No background scheduler, source watcher, learned LLM policy, or production champion.",
        ],
    }
    value["fingerprint"] = digest(value)
    return value


def _accept_probe(probe, observation, *, training_nodes):
    """Validate external observation; never use model candidate vote as truth."""
    if not isinstance(observation, dict):
        raise ValueError("External probe adapter must return an object")
    if (observation.get("schema") != PROBE_SCHEMA or
            observation.get("subject") != probe["subject"] or
            observation.get("destination") != probe["destination"] or
            type(observation.get("expected")) is not bool or
            not isinstance(observation.get("evidence_ref"), str) or
            not observation["evidence_ref"].strip() or
            len(observation["evidence_ref"]) > 500 or
            not isinstance(observation.get("oracle_id"), str) or
            not observation["oracle_id"].strip() or
            len(observation["oracle_id"]) > 128 or
            observation.get("authority") != "EXTERNAL_UNVERIFIED"):
        raise ValueError("Missing or unsafe external probe receipt")
    if probe["subject"] not in training_nodes or probe["destination"] not in training_nodes:
        raise ValueError("Probe crosses train/holdout boundary")
    return {
        "subject": probe["subject"], "destination": probe["destination"],
        "expected": observation["expected"],
    }


def run_controller(training, examples, source, revised_source, workload, *,
                   oracle: Callable | None = None,
                   max_probes: int = 3, trials: int = 2,
                   max_proposals: int = 24):
    """Execute a single bounded autonomous decision cycle, not a daemon.

    - If there is a unique training hypothesis, run the frozen evaluation.
    - If ambiguous, pick the first discriminating question and await a
      caller-provided independent oracle. No oracle -> explicit NEEDS_ORACLE.
    - If the oracle provides a labelled answer, add that TRAINING-only
      observation and reevaluate. A conflicting duplicate stops.
    - Exhaustion of the probe budget yields UNKNOWN, never a chosen path.

    The oracle callback receives ONLY the subject/destination of a proposed
    training probe. It does not receive gold answers, validation sources,
    candidate path predictions, PackSpec secrets, or the held-out graph.
    """
    if type(max_probes) is not int or not 0 <= max_probes <= MAX_PROBES:
        raise ValueError("Invalid probe budget")
    if not isinstance(examples, list) or not 2 <= len(examples) <= MAX_EXAMPLES:
        raise ValueError("Bounded training observations required")
    if oracle is not None and not callable(oracle):
        raise ValueError("Oracle must be a callable or None")
    initial = deepcopy(examples)
    observations = deepcopy(examples)
    # No result claims source completeness or oracle independence.
    graph = training.get("facts") if isinstance(training, dict) else None
    if not isinstance(graph, list):
        raise ValueError("Expected typed training graph")
    training_nodes = {f.get("subject") for f in graph if isinstance(f, dict)} | {
        f.get("object") for f in graph if isinstance(f, dict)}
    events = []
    seen_questions = {(x["subject"], x["destination"]) for x in observations}
    for step in range(max_probes + 1):
        hypothesis = induce_from_examples(
            training, observations, max_proposals=max_proposals)
        events.append({
            "type": "HYPOTHESIS_EXAMINED", "step": step,
            "state": hypothesis["status"],
            "matched_candidate_count": hypothesis["matched_candidate_count"],
            "hypothesis_sha256": digest(hypothesis),
        })
        if hypothesis["status"] == "UNIQUE_TRAINING_HYPOTHESIS":
            # Important: the original held-out workload must not contain
            # predicate_path or any label / gold answer.
            investigation = run_investigation(
                training, observations, source, revised_source, workload,
                trials=trials, max_proposals=max_proposals)
            if investigation.get("experiment") is None:
                return _report("UNRESOLVED", training=training,
                               initial_examples=initial, observed=observations,
                               events=events, remaining_budget=max_probes-step)
            events.append({
                "type": "PAIRED_EXPERIMENT_EXECUTED", "step": step,
                "experiment_sha256": investigation["experiment"]["fingerprint"],
                "candidate_count": len(investigation["experiment"]["results"]),
            })
            return _report(
                "EVALUATED_UNVERIFIED", training=training,
                initial_examples=initial, observed=observations,
                events=events, investigation=investigation,
                remaining_budget=max_probes-step)
        if hypothesis["status"] == "UNRESOLVED":
            return _report("NO_SUPPORTED_OPERATOR", training=training,
                           initial_examples=initial, observed=observations,
                           events=events, remaining_budget=max_probes-step)
        probes = [p for p in hypothesis["discriminating_probes"]
                  if (p["subject"], p["destination"]) not in seen_questions]
        if not probes:
            return _report("NEEDS_NEW_REGIME", training=training,
                           initial_examples=initial, observed=observations,
                           events=events, remaining_budget=max_probes-step)
        selected = probes[0]
        # A selected probe is not an answer; it is a question.
        events.append({
            "type": "PROBE_PROPOSED", "step": step,
            "subject": selected["subject"],
            "destination": selected["destination"],
            "reference_answer": "UNOBSERVED",
        })
        if step >= max_probes:
            return _report("BUDGET_EXHAUSTED", training=training,
                           initial_examples=initial, observed=observations,
                           events=events, remaining_budget=0)
        if oracle is None:
            return _report("NEEDS_ORACLE", training=training,
                           initial_examples=initial, observed=observations,
                           events=events, remaining_budget=max_probes-step)
        # Allow only question coordinates across the callback boundary.
        request = {"subject": selected["subject"],
                   "destination": selected["destination"]}
        result = oracle(deepcopy(request))
        answer = _accept_probe(selected, result, training_nodes=training_nodes)
        key = (answer["subject"], answer["destination"])
        if key in seen_questions:
            raise ValueError("Oracle returned a duplicate observation")
        seen_questions.add(key)
        observations.append(answer)
        events.append({
            "type": "EXTERNAL_OBSERVATION_RECORDED", "step": step,
            "subject": answer["subject"], "destination": answer["destination"],
            "evidence_ref": result["evidence_ref"],
            "oracle_id": result["oracle_id"],
            "observation_sha256": digest(answer),
            "authentication": "UNVERIFIED",
        })
    raise AssertionError("Unreachable bounded controller state")
