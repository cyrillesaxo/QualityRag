"""Retrieve -> label -> gate -> answer/abstain on the synthetic enterprise corpus.

Unlike demo.py and retrieval_benchmark.py, evidence status here is produced by a
labeler from chunk text, not read from the hand labels in corpus.json. The hand
labels are used only as a reference to score the labeler.

Run from repository root:
    PYTHONPATH=sdk/python python examples/enterprise-rag/labeled_pipeline.py
    PYTHONPATH=sdk/python python examples/enterprise-rag/labeled_pipeline.py --llm   # needs ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from qualityrag import evaluate
from qualityrag.labeling import LexicalLabeler, LLMLabeler, anthropic_completer, assess

DATA = json.loads(Path(__file__).with_name("corpus.json").read_text())
OBSERVED = "2026-11-02T10:00:00Z"
AS_OF = "2026-11-02T10:05:00Z"

# Requirement claims are written as the policy author would state them, not copied from chunks.
CLAIMS = {
    "recovery-procedure": "On-call staff are permitted to start automated recovery after a dependency timeout.",
    "eu-screening-control": "Restoration after a sanctions screening dependency failure requires compliance sign-off.",
    "applicable-approval-or-exception": "A documented emergency exception with a recorded approval reference applies.",
}


def passages():
    for d in DATA["documents"]:
        for c in d["chunks"]:
            yield {"id": c["id"], "text": c["text"], "origin": d["origin"],
                   "source_ref": f"{d['id']}#{c['id']}", "observed_at": OBSERVED}


def hand_label(chunk_id: str, requirement_id: str) -> str:
    for d in DATA["documents"]:
        for c in d["chunks"]:
            if c["id"] == chunk_id:
                return c.get("status", "UNKNOWN") if c.get("requirement_id") == requirement_id else "UNKNOWN"
    raise KeyError(chunk_id)


def hand_verdict() -> dict:
    evidence = [{"id": p["id"], "requirement_id": c["requirement_id"], "origin": p["origin"],
                 "source_ref": p["source_ref"], "status": c["status"], "observed_at": OBSERVED}
                for d in DATA["documents"] for c in d["chunks"] if c.get("requirement_id")
                for p in [{"id": c["id"], "origin": d["origin"], "source_ref": f"{d['id']}#{c['id']}"}]]
    return evaluate(DATA["pack"], evidence, as_of=AS_OF)


def run(labeler) -> dict:
    result = assess(DATA["pack"], CLAIMS, passages(), labeler, as_of=AS_OF)
    agree = total = 0
    disagreements = []
    for row in result["label_trace"]:
        expected = hand_label(row["passage_id"], row["requirement_id"])
        total += 1
        if row["status"] == expected:
            agree += 1
        else:
            disagreements.append({"passage": row["passage_id"], "requirement": row["requirement_id"],
                                  "labeler": row["status"], "hand": expected, "score": row["score"]})
    reference = hand_verdict()
    return {"labeler": labeler.name, "verdict": result["verdict"], "hand_label_verdict": reference["verdict"],
            "label_agreement": f"{agree}/{total}", "disagreements": disagreements,
            "findings": result["findings"]}


def main(argv=None) -> list[dict]:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--llm", action="store_true", help="also run the LLM labeler (ANTHROPIC_API_KEY)")
    args = ap.parse_args(argv)
    labelers = [LexicalLabeler(0.6)]
    if args.llm:
        labelers.append(LLMLabeler(anthropic_completer(), name="llm"))
    reports = [run(lab) for lab in labelers]
    for r in reports:
        print(f"[{r['labeler']}] verdict={r['verdict']} (hand labels -> {r['hand_label_verdict']}), "
              f"pair agreement {r['label_agreement']}")
        for f in r["findings"]:
            print(f"    {f['requirement_id']}: {f['verdict']} {f['reasons']}")
        for d in r["disagreements"]:
            print(f"    disagree {d['passage']} / {d['requirement']}: labeler={d['labeler']} hand={d['hand']} score={d['score']}")
    return reports


if __name__ == "__main__":
    main()
