"""Scoring harness for a frozen gold conversation set (US-084 harness; no gold set exists yet).

This module validates a gold file and scores the drift classifier and the trigger inventory
against it. It does not create labels. Without a gold file every metric is UNMEASURED, and a
file marked SYNTHETIC_FIXTURE is scored but never counts as evidence.

Gold file (JSON):
  schema       "qualityrag.conversation-gold/v0.1"
  provenance   "NATURAL" | "INJECTED" | "MIXED" | "SYNTHETIC_FIXTURE"
  annotators   two or more distinct annotator IDs
  agreement    {"raw": 0..1, "reconciled": 0..1}
  threads      [{"thread_id", "turns": [{"turn_id", "actor", "text",
                 "label": "REFINE" | "AMBIGUOUS" | "PIVOT" (USER turns after the first),
                 "constraints": [{"start", "end"}] (USER turns)}]}]
  frozen_sha256  fingerprint of ``threads``, fixed before any system output is seen

    python -m tools.conversation_tree.evaluation /absolute/gold.json
"""
from __future__ import annotations

import json
import sys

from tools.activation_runtime.common import fingerprint, strict_json

from .classify import CLASSIFIER, classify
from .triggers import CRITICAL_FAMILIES, TRIGGER_SET, scan

GOLD_SCHEMA = "qualityrag.conversation-gold/v0.1"
LABELS = ("REFINE", "AMBIGUOUS", "PIVOT")
PROVENANCE = ("NATURAL", "INJECTED", "MIXED", "SYNTHETIC_FIXTURE")
UNMEASURED = {"status": "UNMEASURED", "reason": "No frozen gold set supplied",
              "classifier": CLASSIFIER, "trigger_set": TRIGGER_SET}


def validate(gold):
    if not isinstance(gold, dict) or gold.get("schema") != GOLD_SCHEMA:
        raise ValueError("Unknown gold schema")
    annotators = gold.get("annotators")
    if not isinstance(annotators, list) or len(set(annotators)) < 2:
        raise ValueError("At least two distinct annotators required")
    agreement = gold.get("agreement")
    if (not isinstance(agreement, dict) or
            not all(isinstance(agreement.get(k), (int, float)) and 0 <= agreement[k] <= 1
                    for k in ("raw", "reconciled"))):
        raise ValueError("Raw and reconciled agreement required")
    if gold.get("provenance") not in PROVENANCE:
        raise ValueError("Provenance required")
    threads = gold.get("threads")
    if not isinstance(threads, list) or not threads:
        raise ValueError("Threads required")
    if gold.get("frozen_sha256") != fingerprint(threads):
        raise ValueError("Gold set differs from its frozen fingerprint")
    for thread in threads:
        seen_user = False
        for turn in thread["turns"]:
            if not isinstance(turn.get("text"), str) or turn.get("actor") not in ("USER", "ASSISTANT", "TOOL", "SYSTEM"):
                raise ValueError("Invalid turn")
            if turn["actor"] != "USER":
                continue
            if seen_user and turn.get("label") not in LABELS:
                raise ValueError("Every later USER turn needs a label")
            seen_user = True
            for span in turn.get("constraints", []):
                if not 0 <= span["start"] < span["end"] <= len(turn["text"]):
                    raise ValueError("Invalid constraint span")
    return gold


def score(gold=None):
    """Confusion matrix for the classifier and recall / false-trigger rate for the triggers."""
    if gold is None:
        return dict(UNMEASURED)
    validate(gold)
    matrix = {gold_label: dict.fromkeys(LABELS, 0) for gold_label in LABELS}
    constraints = recalled = triggered = false_triggers = labelled = 0
    for thread in gold["threads"]:
        context = []
        for turn in thread["turns"]:
            if turn["actor"] != "USER":
                continue
            if context:
                matrix[turn["label"]][classify(turn["text"], "\n".join(context))["verdict"]] += 1
                labelled += 1
            context.append(turn["text"])
            hits = [s for s in scan(turn["text"]) if CRITICAL_FAMILIES.intersection(s["families"])]
            wanted = turn.get("constraints", [])
            overlap = lambda a, b: a["start"] < b["end"] and b["start"] < a["end"]
            constraints += len(wanted)
            recalled += sum(1 for c in wanted if any(overlap(c, h) for h in hits))
            triggered += len(hits)
            false_triggers += sum(1 for h in hits if not any(overlap(c, h) for c in wanted))
    correct = sum(matrix[label][label] for label in LABELS)
    synthetic = gold["provenance"] == "SYNTHETIC_FIXTURE"
    return {"status": "SCORED_SYNTHETIC_FIXTURE_NOT_EVIDENCE" if synthetic else "SCORED",
            "evidence": "NONE" if synthetic else "OBSERVED_ON_GOLD",
            "gold": {"frozen_sha256": gold["frozen_sha256"], "provenance": gold["provenance"],
                     "threads": len(gold["threads"]), "annotators": len(set(gold["annotators"])),
                     "agreement": gold["agreement"]},
            "classifier": {"version": CLASSIFIER, "labelled_turns": labelled, "confusion": matrix,
                           "accuracy": correct / labelled if labelled else None},
            "triggers": {"version": TRIGGER_SET, "gold_constraints": constraints,
                         "recall": recalled / constraints if constraints else None,
                         "triggered_spans": triggered,
                         "false_trigger_rate": false_triggers / triggered if triggered else None},
            "note": "No confidence intervals: sample size and intervals belong to the pre-registration (US-085)."}


def main(argv):
    if len(argv) != 2:
        print(json.dumps(score(None), indent=2))
        return 0
    with open(argv[1], "rb") as handle:
        print(json.dumps(score(strict_json(handle.read(), max_bytes=20_000_000)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
