"""Model-free part of the pre-registered comparison (US-085 harness).

Measures one thing only: at a matched context budget, which gold constraints are still
available to the assistant under each arm, and how much retired text it is still shown.
Availability is necessary, not sufficient: whether a model then honors a constraint needs
model runs, which this module does not perform. Arms that need a model are NOT_RUN.

Budget unit: whitespace-separated words, a proxy for tokens.

Arms
  C0_TRANSCRIPT   the whole thread, newest turns first until the budget is spent
  C1_SUMMARY      NOT_RUN (needs a summarizer and a judged endpoint)
  C2_TREE         only the turns in scope of the engine's current branch, newest first
  C3_TREE_GATE    C2, but the gate's required spans are read first, then newest turns
  C4_DIFFERENTIAL NOT_RUN (needs both branches answered by a model)

When the whole thread fits the budget, C0 has every constraint available by construction;
the tree can only tie on this endpoint. Its hypothesized benefit there is fewer stale
violations, which this module cannot observe.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .evaluation import validate
from .tree import ConversationTree

AT = "2026-01-01T00:00:00Z"  # replay clock; ordering comes from custody, not from this value
NOT_RUN = {"C1_SUMMARY": "Needs a summarizer and a judged endpoint",
           "C4_DIFFERENTIAL": "Needs both branches answered by a model"}


def _words(text):
    return len(text.split())


def _replay(tree, thread):
    """Drive the engine over a thread, following the merged reading on doubt. Returns the final branch."""
    current = None
    for turn in thread["turns"]:
        tree.append_turn(turn_id=turn["turn_id"], actor=turn["actor"], content=turn["text"], at=AT)
        if turn["actor"] != "USER":
            if current is not None:
                tree.attach(branch=current, turn_id=turn["turn_id"], at=AT)
        elif current is None:
            tree.open_root(turn_id=turn["turn_id"], at=AT)
            current = "root"
        else:
            moved = tree.advance(branch=current, turn_id=turn["turn_id"], at=AT)
            followed = moved["branches"][-1]  # REFINE: same branch; AMBIGUOUS: merged; PIVOT: isolated
            # Close what is not followed so a long thread stays inside the live-branch cap.
            for name in moved["branches"][:-1] + ([current] if moved["verdict"] == "PIVOT" else []):
                tree.prune(branch=name, witness_turn=turn["turn_id"], reason="Not followed in replay", at=AT)
            current = followed
    return current


def _fill(turns, budget, used=0):
    """Newest-first whole turns that fit the remaining budget."""
    loaded = set()
    for turn in reversed(turns):
        cost = _words(turn["text"])
        if used + cost <= budget:
            loaded.add(turn["turn_id"])
            used += cost
    return loaded, used


def _tally(thread, loaded, spans=()):
    held = lambda turn_id, c: turn_id in loaded or any(
        s["turn_id"] == turn_id and s["start"] < c["end"] and c["start"] < s["end"] for s in spans)
    out = dict(in_force=0, dropped=0, retired=0, retired_exposed=0)
    for turn in thread["turns"]:
        for constraint in turn.get("constraints") or []:
            available = held(turn["turn_id"], constraint)
            if constraint.get("in_force_at_end", True):
                out["in_force"] += 1
                out["dropped"] += not available
            else:
                out["retired"] += 1
                out["retired_exposed"] += available
    return out


def compare(gold, *, budget_words):
    """Constraint availability per arm at one matched budget."""
    validate(gold)
    if type(budget_words) is not int or budget_words < 1:
        raise ValueError("Positive word budget required")
    arms = {name: dict(in_force=0, dropped=0, retired=0, retired_exposed=0, words_used=0)
            for name in ("C0_TRANSCRIPT", "C2_TREE", "C3_TREE_GATE")}

    def add(name, tally, used):
        for key, value in tally.items():
            arms[name][key] += value
        arms[name]["words_used"] += used

    for thread in gold["threads"]:
        with tempfile.TemporaryDirectory() as folder:
            tree = ConversationTree(str(Path(folder) / "t.sqlite"))
            try:
                branch = _replay(tree, thread)
                scope = set(tree.visible_turns(branch)) if branch else set()
                in_scope = [t for t in thread["turns"] if t["turn_id"] in scope]
                loaded, used = _fill(thread["turns"], budget_words)
                add("C0_TRANSCRIPT", _tally(thread, loaded), used)
                loaded, used = _fill(in_scope, budget_words)
                add("C2_TREE", _tally(thread, loaded), used)
                spans, used = [], 0
                texts = {t["turn_id"]: t["text"] for t in thread["turns"]}
                for need in (tree.gate(branch, loaded=set())["required_reads"] if branch else []):
                    cost = _words(texts[need["turn_id"]][need["start"]:need["end"]])
                    if used + cost <= budget_words:
                        spans.append(need)
                        used += cost
                loaded, used = _fill(in_scope, budget_words, used)
                add("C3_TREE_GATE", _tally(thread, loaded, spans), used)
            finally:
                tree.close()
    for stats in arms.values():
        stats["dropped_rate"] = stats["dropped"] / stats["in_force"] if stats["in_force"] else None
        stats["retired_exposure_rate"] = (stats["retired_exposed"] / stats["retired"]
                                          if stats["retired"] else None)
    synthetic = gold["provenance"] == "SYNTHETIC_FIXTURE"
    return {"status": "SCORED_SYNTHETIC_FIXTURE_NOT_EVIDENCE" if synthetic else "SCORED",
            "evidence": "NONE" if synthetic else "OBSERVED_ON_GOLD",
            "endpoint": "CONSTRAINT_AVAILABILITY_ONLY", "budget_words": budget_words,
            "threads": len(gold["threads"]), "arms": arms, "not_run": dict(NOT_RUN),
            "primary_endpoint_stale_constraint_violation": "NOT_RUN: needs model answers",
            "note": "No confidence intervals here; sample size and statistics belong to the pre-registration."}
