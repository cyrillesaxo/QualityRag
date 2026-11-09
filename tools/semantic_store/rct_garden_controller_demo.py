"""Synchronous bounded controller demonstration, with synthetic external labels.

This is NOT a continuously scheduled agent or independent validation.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from rct_garden_controller import run_controller, PROBE_SCHEMA
from rct_garden_demo import fixture
from rct_garden_lifecycle import register_cycle
from store import digest

_LEDGER_DIR = str(Path(__file__).resolve().parents[1] / "research_ledger")
if _LEDGER_DIR not in sys.path:
    sys.path.insert(0, _LEDGER_DIR)
from ledger import initialize, progress, verify_integrity


def make_ambiguous_training():
    source = fixture("training-")
    for i in (0, 1):
        edges = [
            (f"training-s{i}", "alternative_a", f"training-ax{i}"),
            (f"training-ax{i}", "alternative_b", f"training-ay{i}"),
            (f"training-ay{i}", "alternative_c", f"training-t{i}"),
        ]
        for j, (subject, predicate, target) in enumerate(edges):
            source["facts"].append({
                "id": f"alternative-{i}-{j}", "subject": subject,
                "predicate": predicate, "object": target,
                "source_ref": f"alternative-source-{i}-{j}",
            })
    return source


def synthetic_oracle(request):
    """External-to-controller fixture labels; unverified in real deployment."""
    expected = (
        request["subject"].startswith("training-s")
        and request["destination"] == request["subject"].replace(
            "training-s", "training-t")
    )
    return {
        "schema": PROBE_SCHEMA, **request, "expected": expected,
        "oracle_id": "synthetic-fixture-rule",
        "evidence_ref": "fixture:label-rule-v1",
        "authority": "EXTERNAL_UNVERIFIED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--actor", default="synthetic-garden-controller")
    parser.add_argument("--max-probes", type=int, default=3)
    args = parser.parse_args()
    training = make_ambiguous_training()
    before = fixture("live-")
    after = fixture("live-", revised=True)
    examples = [
        {"subject": "training-s0", "destination": "training-t0", "expected": True},
        {"subject": "training-s1", "destination": "training-t1", "expected": True},
        {"subject": "training-s0", "destination": "training-t1", "expected": False},
    ]
    receipt = run_controller(
        training, examples, before, after,
        {"subjects": ["live-s0", "live-s0", "live-s1", "live-s2"]},
        oracle=synthetic_oracle, max_probes=args.max_probes)
    Path(args.receipt).write_text(json.dumps(receipt, indent=2) + "\n",
                                  encoding="utf-8")
    claim_id = None
    if receipt["investigation"] is not None:
        experiment = receipt["investigation"]["experiment"]
        with sqlite3.connect(args.db) as db:
            initialize(db)
            item = register_cycle(
                db, experiment,
                sources={
                    "training": digest(training),
                    "source": digest(before),
                    "revised": digest(after),
                },
                evidence_uri=args.uri, actor=args.actor)
            claim_id = item["claim_id"]
            if not verify_integrity(db)["consistent"]:
                raise ValueError("Ledger integrity failure")
    print(json.dumps({
        "controller_status": receipt["status"],
        "probe_count": receipt["external_probe_count"],
        "research_claim": claim_id,
        "candidate_count": (
            len(receipt["investigation"]["experiment"]["results"])
            if receipt["investigation"] else 0),
        "qualityrag_admission": receipt["qualityrag_admission"],
        "promotion_authorized": receipt["promotion_authorized"],
        "fixture_only": True,
    }, indent=2))


if __name__ == "__main__":
    main()
