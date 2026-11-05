"""Demonstration: training-only grammar induction plus joint activation search.

Uses synthetic facts only; it does not demonstrate AI-agent autonomy or
native FF-RCT performance. No production champion is promoted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from rct_garden_coevolution import run_investigation


def fixture(prefix, *, revised=False):
    facts = []
    for i in range(6):
        transitions = [
            (f"{prefix}s{i}", "belongs", f"{prefix}m{i}"),
            (f"{prefix}m{i}", "derives", f"{prefix}n{i}"),
            (f"{prefix}n{i}", "governs", f"{prefix}t{i}"),
        ]
        for j, (subject, predicate, target) in enumerate(transitions):
            facts.append({
                "id": f"{prefix}fact-{i}-{j}",
                "subject": subject, "predicate": predicate,
                "object": target, "source_ref": f"{prefix}source-{i}-{j}",
            })
    if revised:
        facts.append({
            "id": f"{prefix}revision", "subject": f"{prefix}n0",
            "predicate": "governs", "object": f"{prefix}revised-target",
            "source_ref": f"{prefix}revision-source",
        })
    return {"schema": "rct.structured-ast/v1", "facts": facts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", help="Save research receipt, including all trials")
    p.add_argument("--trials", type=int, default=3)
    args = p.parse_args()
    training = fixture("training-")
    observations = [
        {"subject": "training-s0", "destination": "training-t0",
         "expected": True},
        {"subject": "training-s1", "destination": "training-t1",
         "expected": True},
        {"subject": "training-s0", "destination": "training-t1",
         "expected": False},
    ]
    workload = {"subjects": [
        "live-s0", "live-s0", "live-s0", "live-s1",
        "live-s2", "live-s0", "live-s3",
    ]}
    receipt = run_investigation(
        training, observations, fixture("live-"), fixture("live-", revised=True),
        workload, trials=args.trials)
    if args.output:
        Path(args.output).write_text(json.dumps(receipt, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({
        "hypothesis_status": receipt["hypothesis"]["status"],
        "selected_operator": receipt["hypothesis"]["selected_predicate_path"],
        "experiment_status": receipt["status"],
        "paired_candidates": len(receipt["experiment"]["results"])
             if receipt["experiment"] else 0,
        "pareto_candidate_indices": receipt["experiment"]["pareto_candidate_indices"]
             if receipt["experiment"] else [],
        "champion": receipt["experiment"]["champion"]
             if receipt["experiment"] else None,
        "qualityrag_admission": receipt["qualityrag_admission"],
        "limitations": [
            "Synthetic examples and finite typed-graph semantics only",
            "Compositional operator family and activation algorithm predeclared",
            "No native FF-RCT or authenticated semantic admission",
            "No live AI agent, model inference, or autonomous Garden scheduler",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
