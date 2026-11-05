"""Offline capability-frontier evaluator. Does not invoke or certify an LLM."""
from __future__ import annotations
import hashlib
import json

POLICIES = ("baseline", "tools", "grammar", "garden")
SCHEMA = "qualityrag.capability-frontier/v0.1"
METRICS = ("tokens_in", "tokens_out", "tool_calls", "wall_ms", "cost_microusd")

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def evaluate(cases, runs, *, budget, min_trials=3, success_threshold=0.8):
    """Evaluate paired, independently audited model outputs against frozen answers.

    This code checks consistency, not whether an upstream auditor is trustworthy.
    """
    if not isinstance(cases, list) or not 0 < len(cases) <= 10000:
        raise ValueError("Invalid cases")
    if not isinstance(runs, list) or not 0 < len(runs) <= 100000:
        raise ValueError("Invalid runs")
    if type(min_trials) is not int or not 2 <= min_trials <= 100:
        raise ValueError("Invalid trial count")
    if not isinstance(success_threshold, (int, float)) or not 0 < success_threshold <= 1:
        raise ValueError("Invalid reliability threshold")
    if not isinstance(budget, dict) or any(type(budget.get(k)) is not int or budget[k] < 0 for k in METRICS):
        raise ValueError("Invalid budget")
    case_by_id = {}
    for case in cases:
        if not isinstance(case, dict) or any(not isinstance(case.get(k), str) or not case[k]
            for k in ("id", "family", "regime", "split")) or "expected" not in case:
            raise ValueError("Malformed case")
        if case["split"] not in ("development", "holdout") or case["id"] in case_by_id:
            raise ValueError("Invalid split or duplicate case")
        case_by_id[case["id"]] = case
    table, pair_setup = {}, {}
    for row in runs:
        if not isinstance(row, dict) or row.get("case_id") not in case_by_id or row.get("policy") not in POLICIES:
            raise ValueError("Unknown case or policy")
        if type(row.get("trial")) is not int or row["trial"] < 1:
            raise ValueError("Invalid trial")
        if any(type(row.get(k)) is not int or row[k] < 0 for k in METRICS):
            raise ValueError("Invalid metrics")
        if any(row[k] > budget[k] for k in METRICS):
            raise ValueError("Budget exceeded")
        if (type(row.get("constraint_violations")) is not int or row["constraint_violations"] < 0
                or "output" not in row or not isinstance(row.get("auditor_ref"), str)
                or not row["auditor_ref"].strip() or not isinstance(row.get("model_id"), str)
                or not row["model_id"] or not isinstance(row.get("tools_fingerprint"), str)
                or not row["tools_fingerprint"]):
            raise ValueError("Missing independent execution fields")
        key = (row["case_id"], row["trial"], row["policy"])
        if key in table:
            raise ValueError("Duplicate run")
        table[key] = row
        pair_setup.setdefault((row["case_id"], row["trial"]), set()).add(
            (row["model_id"], row["tools_fingerprint"]))
    if any(len(x) != 1 for x in pair_setup.values()):
        raise ValueError("Model/tool configuration not paired")
    trials = sorted({key[1] for key in table})
    if len(trials) < min_trials:
        raise ValueError("Insufficient trials")
    for cid in case_by_id:
        for trial in trials:
            for policy in POLICIES:
                if (cid, trial, policy) not in table:
                    raise ValueError("Unpaired trial")
    results, success = [], {}
    for cid, case in sorted(case_by_id.items()):
        for policy in POLICIES:
            subset = [table[(cid, trial, policy)] for trial in trials]
            passed = sum(row["output"] == case["expected"] and row["constraint_violations"] == 0
                         for row in subset)
            rate = passed / len(trials)
            success[(cid, policy)] = rate >= success_threshold
            results.append({
                "case_id": cid, "family": case["family"], "regime": case["regime"],
                "split": case["split"], "policy": policy, "success_rate": rate,
                "mean_tokens": sum(row["tokens_in"] + row["tokens_out"] for row in subset) / len(subset),
                "mean_tool_calls": sum(row["tool_calls"] for row in subset) / len(subset),
                "mean_wall_ms": sum(row["wall_ms"] for row in subset) / len(subset),
                "mean_cost_microusd": sum(row["cost_microusd"] for row in subset) / len(subset),
            })
    holdout = [cid for cid, case in case_by_id.items() if case["split"] == "holdout"]
    frontier = [cid for cid in holdout if success[(cid, "garden")] and not success[(cid, "baseline")]]
    regressions = [cid for cid in holdout if success[(cid, "baseline")] and not success[(cid, "garden")]]
    return {
        "schema": SCHEMA, "cases_sha256": digest(cases),
        "runs_sha256": digest(runs), "budget_sha256": digest(budget),
        "trial_ids": trials, "success_threshold": success_threshold,
        "holdout_cases": len(holdout), "frontier_expansions": [
            {"case_id": cid, "family": case_by_id[cid]["family"], "regime": case_by_id[cid]["regime"]}
            for cid in frontier], "regressions": regressions, "per_case": results,
        "limitations": [
            "Exact output matching is not an independently verified semantic oracle.",
            "Caller-supplied measurement and auditor identifiers require trusted provenance.",
            "No LLM was run by this evaluator; this is not evidence of intrinsic model improvement.",
        ],
    }

def assess_operator(proposal, experiment, *, independently_reviewed=False):
    """Never promote without actual canonical APX admission."""
    if not isinstance(proposal, dict) or not isinstance(experiment, dict):
        raise ValueError("Invalid proposal or experiment")
    required = ("id", "grammar_version", "function", "source_regime",
                "target_regime", "preserved_constraints", "counterexamples", "pack_sha256")
    if any(k not in proposal for k in required) or not isinstance(proposal["preserved_constraints"], list) or not proposal["preserved_constraints"]:
        raise ValueError("Missing preservation contract")
    if experiment.get("schema") != SCHEMA:
        raise ValueError("Wrong experiment receipt")
    families = {r["family"] for r in experiment.get("frontier_expansions", [])}
    reasons = []
    if experiment.get("holdout_cases", 0) < 4:
        reasons.append("INSUFFICIENT_HOLDOUT")
    if len(families) < 2:
        reasons.append("NO_CROSS_FAMILY_TRANSFER")
    if experiment.get("regressions"):
        reasons.append("BASELINE_REGRESSION")
    if not independently_reviewed:
        reasons.append("UNREVIEWED")
    reasons.append("CANONICAL_APX_ADMISSION_REQUIRED")
    return {"operator_id": proposal["id"], "status": "CANDIDATE",
            "promotion_authorized": False, "reasons": reasons,
            "proposal_sha256": digest(proposal),
            "experiment_sha256": digest(experiment)}
