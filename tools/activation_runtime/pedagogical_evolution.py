"""Pedagogical research adapter; never a production promotion mechanism.

Reuse the Gardener and content-addressed evidence store. Supplied aggregate
observations are descriptive only; no learner identifiers enter this adapter.
"""
from __future__ import annotations
from math import isfinite
from .common import canonical, fingerprint, identity, HEX
from .gardener import Gardener, ledger
from .artifacts import ArtifactStore

ARMS = ("standard", "ladder", "adaptive", "embodied", "historical", "interactive_transfer")


def describe_pedagogical_cycle(report, *, protocol_sha256, representation_sha256):
    for value in (protocol_sha256, representation_sha256):
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise ValueError("Pinned protocol and representation required")
    if (not isinstance(report, dict) or report.get("studyDesign") != "EXPERIENTIAL_COMPARISON"
            or report.get("primaryOutcome") != "delayed_transfer_per_learning_minute"
            or report.get("outcomeKind") not in ("observed", "simulated")
            or report.get("promotionAuthorized") is not False):
        raise ValueError("Versioned descriptive study report required")
    identity(report.get("protocolId"))
    rows = report.get("arms")
    if not isinstance(rows, list) or len(rows) != len(ARMS):
        raise ValueError("Six comparator arms required")
    arms = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("arm") not in ARMS or row["arm"] in arms:
            raise ValueError("Invalid comparator arm")
        assigned, assessed, missing = (row.get(k) for k in ("assigned", "delayedAssessed", "missingDelayed"))
        rate = row.get("meanDelayedTransferPerMinute")
        if (any(type(n) is not int or not 0 <= n <= 10000 for n in (assigned, assessed, missing))
                or assessed + missing != assigned
                or (assessed == 0 and rate != "UNKNOWN")
                or (assessed > 0 and (type(rate) not in (int, float) or not isfinite(rate) or rate < 0))):
            raise ValueError("Invalid study denominator or rate")
        arms[row["arm"]] = {"assigned": assigned, "assessed": assessed, "missing": missing, "rate": rate}
    blockers = ["INDEPENDENT_REVIEW_REQUIRED", "SEMANTIC_FIDELITY_UNVERIFIED",
                "FRESH_CONFIRMATION_REQUIRED", "NO_CAUSAL_ESTIMATE"]
    if report["outcomeKind"] == "simulated":
        blockers.append("SIMULATED_ONLY")
    if report.get("comparableMaterials") is not True:
        blockers.append("MATERIAL_COMPARABILITY_UNESTABLISHED")
    if any(a["missing"] or not a["assigned"] for a in arms.values()):
        blockers.append("INCOMPLETE_FOLLOWUP_OR_ARM")
    # No ranking or winner from unverified aggregate outcomes. Preserve all
    # negative/zero results and missing denominators for subsequent hypotheses.
    result = {"schema": "qualityrag.pedagogical-cycle/v1",
              "protocol_id": report["protocolId"], "protocol_sha256": protocol_sha256,
              "representation_sha256": representation_sha256,
              "outcome_kind": report["outcomeKind"], "arms": arms,
              "material_comparability": "CALLER_REPORTED_NOT_VERIFIED",
              "blockers": sorted(blockers), "status": "RESEARCH_ONLY",
              "effectiveness": "NOT_ESTABLISHED", "selected": None,
              "can_promote": False, "can_release": False, "can_generate": False}
    return {**result, "fingerprint": fingerprint(result)}


def record_pedagogical_cycle(garden, store, *, branch, actor, at, report,
                             protocol_sha256, representation_sha256):
    if not isinstance(garden, Gardener) or not isinstance(store, ArtifactStore):
        raise ValueError("Host-owned research ledger and artifact store required")
    identity(branch); identity(actor)
    result = describe_pedagogical_cycle(report, protocol_sha256=protocol_sha256,
                                        representation_sha256=representation_sha256)
    state = garden.replay()
    if branch not in state["branches"]:
        raise ValueError("Existing hypothesis branch required")
    first = state["events"][state["branches"][branch]["events"][0]]
    if first["source_sha256"] != representation_sha256:
        raise ValueError("Hypothesis representation revision mismatch")
    # The protocol pin is an asserted reference, not proof of registration.
    address = store.put(canonical(result))
    eid = "ped-evidence-" + address
    event_id = "ped-test-" + fingerprint([branch, address])
    if event_id in state["events"]:
        return result
    if not garden.db.execute("SELECT 1 FROM research_evidence WHERE evidence_id=?", (eid,)).fetchone():
        ledger.evidence(garden.db, evidence_id=eid, kind="TEST_RESULT",
                        uri="sha256://" + address, content_sha256=address,
                        description="Supplied descriptive pedagogical report; unverified and research only", at=at)
    garden.append(event_id=event_id, operation="TEST", branch=branch, actor=actor,
                  source_sha256=representation_sha256, source_ref="sha256://" + address,
                  statement="Descriptive pedagogical comparison recorded; no efficacy or promotion claim.",
                  at=at, evidence_ids=[eid])
    return result
