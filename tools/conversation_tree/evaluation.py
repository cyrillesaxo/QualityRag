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
  A constraint may carry ``"in_force_at_end": false`` when a later turn retired it (default true).

Producing a gold set (no step creates a label for you):
  1. template(threads)            -> one blank annotation file per annotator
  2. each annotator fills labels and constraint spans independently
  3. reconcile(first, second)     -> raw agreement, the disagreements, and a draft
  4. an expert resolves the draft's open items
  5. freeze(threads, ...)         -> the gold file, fingerprinted

    python -m tools.conversation_tree.evaluation score /absolute/gold.json
    python -m tools.conversation_tree.evaluation template /absolute/threads.json
    python -m tools.conversation_tree.evaluation reconcile /absolute/a.json /absolute/b.json
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


ANNOTATION_SCHEMA = "qualityrag.conversation-annotation/v0.1"


def thread_from_tree(tree, thread_id):
    """Export a stored conversation as a thread to annotate. Non-text turns are refused, not skipped."""
    turns = []
    for turn in tree.turns():
        try:
            text = turn["content"].decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Turn %s is not text and cannot be annotated" % turn["turn_id"]) from None
        turns.append({"turn_id": turn["turn_id"], "actor": turn["actor"], "text": text})
    return {"thread_id": thread_id, "turns": turns}


def _source(threads):
    """Fingerprint of the text being annotated, independent of any labels."""
    return fingerprint([[t["thread_id"], [[u["turn_id"], u["actor"], u["text"]] for u in t["turns"]]]
                        for t in threads])


def template(threads):
    """Blank annotation file: every later USER turn needs a label, every USER turn a constraint list."""
    out = []
    for thread in threads:
        seen_user, turns = False, []
        for turn in thread["turns"]:
            if not isinstance(turn.get("text"), str) or turn.get("actor") not in ("USER", "ASSISTANT", "TOOL", "SYSTEM"):
                raise ValueError("Invalid turn")
            item = {"turn_id": turn["turn_id"], "actor": turn["actor"], "text": turn["text"]}
            if turn["actor"] == "USER":
                item["constraints"] = None  # to fill: [] or [{"start", "end"}]
                if seen_user:
                    item["label"] = None    # to fill: REFINE | AMBIGUOUS | PIVOT
                seen_user = True
            turns.append(item)
        out.append({"thread_id": thread["thread_id"], "turns": turns})
    return {"schema": ANNOTATION_SCHEMA, "annotator": None, "source_sha256": _source(out), "threads": out}


def _chars(spans):
    return {i for span in spans for i in range(span["start"], span["end"])}


def reconcile(first, second):
    """Compare two independent annotations. Agreements are kept; disagreements are left open for an expert."""
    for item in (first, second):
        if item.get("schema") != ANNOTATION_SCHEMA or not isinstance(item.get("annotator"), str) or not item["annotator"]:
            raise ValueError("Each file needs the annotation schema and an annotator ID")
        if item.get("source_sha256") != _source(item["threads"]):
            raise ValueError("Annotated text differs from the template it came from")
    if first["annotator"] == second["annotator"] or first["source_sha256"] != second["source_sha256"]:
        raise ValueError("Two different annotators must label the same text")
    labelled = same = union = both = 0
    disagreements, draft = [], []
    for left, right in zip(first["threads"], second["threads"]):
        turns = []
        for a, b in zip(left["turns"], right["turns"]):
            item = {"turn_id": a["turn_id"], "actor": a["actor"], "text": a["text"]}
            if a["actor"] == "USER":
                if a.get("constraints") is None or b.get("constraints") is None:
                    raise ValueError("Unfilled constraints in %s" % a["turn_id"])
                ca, cb = _chars(a["constraints"]), _chars(b["constraints"])
                union, both = union + len(ca | cb), both + len(ca & cb)
                agreed = ca == cb
                item["constraints"] = a["constraints"] if agreed else None
                if not agreed:
                    disagreements.append({"thread_id": left["thread_id"], "turn_id": a["turn_id"],
                                          "field": "constraints", "first": a["constraints"],
                                          "second": b["constraints"]})
                if "label" in a:
                    if a["label"] not in LABELS or b.get("label") not in LABELS:
                        raise ValueError("Unfilled or invalid label in %s" % a["turn_id"])
                    labelled += 1
                    same += a["label"] == b["label"]
                    item["label"] = a["label"] if a["label"] == b["label"] else None
                    if a["label"] != b["label"]:
                        disagreements.append({"thread_id": left["thread_id"], "turn_id": a["turn_id"],
                                              "field": "label", "first": a["label"], "second": b["label"]})
            turns.append(item)
        draft.append({"thread_id": left["thread_id"], "turns": turns})
    return {"annotators": [first["annotator"], second["annotator"]],
            "agreement": {"raw": same / labelled if labelled else 1.0,
                          "raw_constraint_chars": both / union if union else 1.0,
                          "labelled_turns": labelled},
            "disagreements": disagreements, "draft_threads": draft,
            "next": "An expert resolves every null in draft_threads, then freeze()."}


def freeze(threads, *, annotators, agreement, reconciled, provenance):
    """Fingerprint the resolved threads as the gold set. Refuses while anything is still open."""
    for thread in threads:
        for turn in thread["turns"]:
            if turn["actor"] == "USER" and (turn.get("constraints") is None or turn.get("label", "") is None):
                raise ValueError("Unresolved item in %s" % turn["turn_id"])
    gold = {"schema": GOLD_SCHEMA, "provenance": provenance, "annotators": list(annotators),
            "agreement": {**agreement, "reconciled": reconciled}, "threads": threads,
            "frozen_sha256": fingerprint(threads)}
    return validate(gold)


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


def _load(path):
    with open(path, "rb") as handle:
        return strict_json(handle.read(), max_bytes=20_000_000)


def main(argv):
    command, paths = (argv[1], argv[2:]) if len(argv) > 1 else ("score", [])
    if command == "score" and len(paths) <= 1:
        result = score(_load(paths[0]) if paths else None)
    elif command == "template" and len(paths) == 1:
        result = template(_load(paths[0]))
    elif command == "reconcile" and len(paths) == 2:
        result = reconcile(_load(paths[0]), _load(paths[1]))
    else:
        print("usage: evaluation [score [gold.json] | template threads.json | reconcile a.json b.json]",
              file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
