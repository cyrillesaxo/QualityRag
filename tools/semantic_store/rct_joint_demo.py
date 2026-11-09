"""Reproducible synthetic demonstration of joint grammar/activation search.

The output is a local research comparison, NOT a certified performance claim.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from rct_joint_optimizer import evaluate_joint_search


def fixture(prefix: str, *, revised=False):
    facts = []
    for i in range(8):
        facts.extend((
            {"id": f"{prefix}left-{i}", "subject": f"{prefix}subject-{i}",
             "predicate": "projects_to", "object": f"{prefix}middle-{i}",
             "source_ref": f"{prefix}ref-L{i}"},
            {"id": f"{prefix}right-{i}", "subject": f"{prefix}middle-{i}",
             "predicate": "belongs_to", "object": f"{prefix}target-{i % 3}",
             "source_ref": f"{prefix}ref-R{i}"},
            {"id": f"{prefix}other-{i}", "subject": f"{prefix}subject-{i}",
             "predicate": "unrelated", "object": f"{prefix}noise-{i}",
             "source_ref": f"{prefix}ref-N{i}"},
        ))
    if revised:
        facts.append(
            {"id": f"{prefix}revision-1", "subject": f"{prefix}middle-0",
             "predicate": "belongs_to", "object": f"{prefix}new-target",
             "source_ref": f"{prefix}change-1"})
    return {"schema": "rct.structured-ast/v1", "facts": facts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", help="Save complete research receipt as JSON")
    p.add_argument("--trials", type=int, default=3)
    args = p.parse_args()
    workload = {"predicate_pair": ["projects_to", "belongs_to"],
                "subjects": [f"live-subject-{i}" for i in range(5)],
                "repetitions": 5}
    receipt = evaluate_joint_search(
        fixture("train-"), fixture("live-"), fixture("live-", revised=True),
        workload, trials=args.trials)
    if args.output:
        Path(args.output).write_text(json.dumps(receipt, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({
        "schema": receipt["schema"],
        "candidate_count": len(receipt["results"]),
        "nondominated": receipt["pareto_candidates"],
        "measurements": [
            {"grammar": r["grammar"], "activation": r["activation"],
             "median_total_ns": r["median_total_ns"],
             "median_peak_serialized_bytes": r["median_peak_bytes"]}
            for r in receipt["results"]],
        "qualityrag_admission": receipt["qualityrag_admission"],
        "champion": receipt["champion"],
        "limitations": [
            "Synthetic, tiny, Python/SQLite runtime-dependent measurements",
            "Fixed grammar and activation templates; no autonomous evolution",
            "Reference zlib frame is not native FF-RCT",
            "No production admission or comparative superiority established",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
