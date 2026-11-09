"""Read-only Semantic Gardener projection over QualityRag's existing ledger.

This is a view/API payload builder, not a second event store or a live UI.
Only ledger rows, previously validated for hash consistency, are projected.
No verified semantic coordinates, admission, or evidence independence inferred.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_LEDGER = Path(__file__).resolve().parents[1] / "research_ledger"
if str(_LEDGER) not in sys.path:
    sys.path.insert(0, str(_LEDGER))
from ledger import progress, verify_integrity  # noqa: E402

SCHEMA = "rct.semantic-gardener-projection/v0.1"
SUPPORTED = {"UNVERIFIED", "INCONCLUSIVE", "IMPLEMENTED", "TESTED",
             "REFUTED", "SUPERSEDED", "VALIDATED"}
CLAIM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def project_garden(db, *, project="QualityRag", maximum_claims=200,
                   maximum_events=2000):
    """Return bounded UI tree nodes, event stream, and typed links.

    A branch is a projection of a claim, not a guarantee of a strict tree.
    Provenance DAG edges are retained; multiple parents are not collapsed.
    The ledger's VALIDATED label is displayed only if present, never invented.
    """
    if not isinstance(project, str) or not CLAIM_ID.fullmatch(project):
        raise ValueError("Invalid project")
    if type(maximum_claims) is not int or not 1 <= maximum_claims <= 2000:
        raise ValueError("Invalid claim limit")
    if type(maximum_events) is not int or not 1 <= maximum_events <= 10000:
        raise ValueError("Invalid event limit")
    integrity = verify_integrity(db)
    if not integrity["consistent"]:
        raise ValueError("Research ledger integrity failure")
    report = progress(db, project=project)
    claims = report["claims"]
    if len(claims) > maximum_claims:
        raise ValueError("Projection claim limit exceeded")
    if sum(len(x["events"]) for x in claims) > maximum_events:
        raise ValueError("Projection event limit exceeded")
    branches, events, relations = [], [], []
    visible = {item["claim_id"] for item in claims}
    for item in claims:
        assessments = item["events"]
        status = item["status"]
        if status not in SUPPORTED:
            raise ValueError("Unknown ledger assessment")
        branches.append({
            "id": item["claim_id"],
            "kind": item["kind"],
            "statement": item["statement"],
            "assessment": status,
            "active_research": status not in {"SUPERSEDED", "REFUTED"},
            # Active research is NOT evidence that a claim is admitted.
            "admission": "NOT_ESTABLISHED",
            "event_count": len(assessments),
        })
        for event in assessments:
            events.append({
                "id": event["event_id"],
                "branch_id": item["claim_id"],
                "assessment": event["assessment"],
                "reason": event["reason"],
                "at": event["observed_at"],
                "actor": event["actor"],
                "evidence_ids": event["evidence_ids"],
                "previous_event_hash": event["previous_event_hash"],
                "event_hash": event["event_hash"],
            })
        for relation in item["links"]:
            relations.append({
                "from": item["claim_id"], "to": relation["to"],
                "relation": relation["relation"],
                "target_visible": relation["to"] in visible,
                "epistemic_weight": "UNDETERMINED",
            })
    events.sort(key=lambda x: (x["at"], x["id"]))
    relations.sort(key=lambda x: (x["from"], x["to"], x["relation"]))
    branches.sort(key=lambda x: x["id"])
    garden = [b for b in branches if b["id"].startswith("garden.")]
    return {
        "schema": SCHEMA, "project": project,
        "branches": branches, "events": events, "relations": relations,
        "summary": {
            "branches": len(branches), "garden_branches": len(garden),
            "events": len(events), "relations": len(relations),
            "unresolved": sum(b["assessment"] in {"UNVERIFIED", "INCONCLUSIVE"}
                              for b in branches),
        },
        "ledger_integrity": "CONSISTENT",
        "authority": "READ_ONLY_PROJECTION",
        "qualityrag_admission": "INCONCLUSIVE",
        "promotion_authorized": False,
        "limitations": [
            "Ledger checksums protect accidental modification, not malicious database owners.",
            "Claims and events are caller-authored; no independent evidence authentication.",
            "Semantic 12G/k-b-c-tau and FF-RCT fields are not inferred from claim labels.",
            "This is a view of an existing ledger, not the actual deployed Garden UI.",
            "Visual branches are only one projection of the typed lineage graph.",
        ],
    }
