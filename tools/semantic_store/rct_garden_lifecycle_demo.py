"""Run a bounded Garden experiment and demonstrate source-dependent reopening.

Synthetic facts, local SQLite; not a scheduled autonomous Garden.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from rct_garden_coevolution import run_investigation
from rct_garden_demo import fixture
from rct_garden_lifecycle import register_cycle, replay_after_revision
from store import digest

from sys import path
_LEDGER = str(Path(__file__).resolve().parents[1] / "research_ledger")
if _LEDGER not in path:
    path.insert(0, _LEDGER)
from ledger import initialize, progress, verify_integrity


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="Local research SQLite path")
    p.add_argument("--receipt", required=True, help="Write raw research receipt JSON")
    p.add_argument("--uri", required=True, help="Retrievable URI for stored receipt")
    p.add_argument("--actor", default="garden-researcher")
    a = p.parse_args()
    train = fixture("training-")
    before = fixture("live-")
    after = fixture("live-", revised=True)
    examples = [
        {"subject": "training-s0", "destination": "training-t0", "expected": True},
        {"subject": "training-s1", "destination": "training-t1", "expected": True},
        {"subject": "training-s0", "destination": "training-t1", "expected": False},
    ]
    investigation = run_investigation(
        train, examples, before, after,
        {"subjects": ["live-s0", "live-s0", "live-s1", "live-s2"]},
        trials=2)
    experiment = investigation["experiment"]
    if not experiment:
        raise ValueError("No unique training hypothesis; explicit probe required")
    Path(a.receipt).write_text(json.dumps(investigation, indent=2) + "\n",
                               encoding="utf-8")
    sources = {
        "training": digest(train), "source": digest(before),
        "revised": digest(after),
    }
    db = sqlite3.connect(a.db)
    try:
        initialize(db)
        opened = register_cycle(db, experiment, sources=sources,
                                evidence_uri=a.uri, actor=a.actor)
        next_source = dict(after)
        next_source["facts"] = [dict(x) for x in after["facts"]]
        next_source["facts"].append({
            "id": "live-third-revision", "subject": "live-n1",
            "predicate": "governs", "object": "live-later-target",
            "source_ref": "live-new-revision"})
        replayed = replay_after_revision(
            db, opened["claim_id"], training=train, examples=examples,
            source=before, revised_source=next_source,
            workload={"subjects": ["live-s0", "live-s0", "live-s1", "live-s2"]},
            actor=a.actor, observation_uri=a.uri, receipt_uri=a.uri, trials=2)
        print(json.dumps({
            "schema": "rct.garden-lifecycle-demo/v0.1",
            "hypothesis": investigation["hypothesis"]["status"],
            "experimental_candidates": len(experiment["results"]),
            "experiment_claim": opened["claim_id"],
            "replay_status": replayed["status"],
            "replayed": replayed["replayed"],
            "new_claim_id": replayed.get("new_claim_id"),
            "ledger_event_count": len(next(
                x for x in progress(db)["claims"]
                if x["claim_id"] == opened["claim_id"])["events"]),
            "ledger_claim_count": progress(db)["counts"]["total"],
            "ledger_integrity": verify_integrity(db)["consistent"],
            "qualityrag_admission": "INCONCLUSIVE",
            "promotion_authorized": False,
        }, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
