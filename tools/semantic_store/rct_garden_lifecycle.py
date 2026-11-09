"""Source-bound, append-only Garden research lifecycle (experimental).

Uses the existing research ledger; this module does not create a new history
database, attest source authenticity, approve a candidate, or run a daemon.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from store import digest
from rct_garden_coevolution import SCHEMA as EXPERIMENT_SCHEMA

_LEDGER_DIR = Path(__file__).resolve().parents[1] / "research_ledger"
if str(_LEDGER_DIR) not in sys.path:
    sys.path.insert(0, str(_LEDGER_DIR))
from ledger import claim, evidence, assess, link, verify_integrity, LedgerError  # noqa: E402

SCHEMA = "rct.garden-lifecycle/v0.1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SOURCE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


def _validate_sources(sources):
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 50:
        raise ValueError("Bounded source manifest required")
    if any(not isinstance(k, str) or not _SOURCE.fullmatch(k) or
           not isinstance(v, str) or not _HASH.fullmatch(v)
           for k, v in sources.items()):
        raise ValueError("Source refs and content SHA-256 must be valid")
    return dict(sorted(sources.items()))


def _validate_receipt(receipt):
    if not isinstance(receipt, dict) or receipt.get("schema") != EXPERIMENT_SCHEMA:
        raise ValueError("Unrecognized experiment receipt")
    body = dict(receipt)
    fp = body.pop("fingerprint", None)
    if not isinstance(fp, str) or fp != digest(body):
        raise ValueError("Receipt fingerprint mismatch")
    if (receipt.get("qualityrag_admission") != "INCONCLUSIVE"
            or receipt.get("promotion_authorized") is not False
            or receipt.get("can_generate") is not False
            or receipt.get("champion") is not None
            or receipt.get("status") != "CANDIDATES_EVALUATED"
            or not receipt.get("results")
            or any(x.get("qualityrag_admission") != "INCONCLUSIVE" or
                   x.get("promotion_authorized") is not False
                   for x in receipt["results"])):
        raise ValueError("Experiment is not an unpromoted bounded candidate")
    return fp


def _event(db, *, claim_id, event_id, assessment, reason, evidence_id, actor):
    return assess(db, event_id=event_id, claim_id=claim_id,
                  assessment=assessment, reason=reason,
                  actor=actor, evidence_ids=[evidence_id])


def register_cycle(db, receipt, *, sources, evidence_uri, actor, project="QualityRag",
                   receipt_content_sha256=None):
    """Record one source-bound experimental investigation, never validation.

    Receipt hashes and source identities come from the caller and are not
    cryptographic origin attestations. Duplicate registrations fail closed.
    """
    fp = _validate_receipt(receipt)
    sources = _validate_sources(sources)
    expected = {
        "training": receipt.get("training_sha256"),
        "source": receipt.get("source_sha256"),
        "revised": receipt.get("revised_sha256"),
    }
    if any(sources.get(k) != sha for k, sha in expected.items()):
        raise ValueError("Source manifest must bind exact train/source/revised digests")
    if receipt_content_sha256 is not None and (
            not isinstance(receipt_content_sha256, str) or
            not _HASH.fullmatch(receipt_content_sha256)):
        raise ValueError("Invalid receipt file SHA-256")
    key = fp[:24]
    cid = "garden.cycle." + key
    eid = "garden.cycle-evidence." + key
    event_id = "garden.cycle-open." + key
    # Existing ledger APIs enforce immutable claims and referenceable
    # evidence IDs. They do not guarantee multi-write atomicity here.
    claim(db, claim_id=cid, project=project, kind="EXPERIMENT",
          statement="Bounded candidate grammar and activation experiment; "
                    "not a certified semantic or production improvement.")
    evidence(db, evidence_id=eid, kind="MEASUREMENT", uri=evidence_uri,
             description="Research-only experiment receipt; not independently authenticated",
             content_sha256=receipt_content_sha256,
             metadata={"receipt_schema": EXPERIMENT_SCHEMA,
                       "source_manifest": sources,
                       "experiment_fingerprint": fp})
    _event(db, claim_id=cid, event_id=event_id, assessment="INCONCLUSIVE",
           reason="Candidate measured; FF-RCT/PackSpec/independent validation not complete",
           evidence_id=eid, actor=actor)
    if not verify_integrity(db)["consistent"]:
        raise ValueError("Ledger integrity check failed")
    return {
        "schema": SCHEMA, "claim_id": cid, "event_id": event_id,
        "experiment_sha256": fp, "source_manifest_sha256": digest(sources),
        "assessment": "INCONCLUSIVE", "promotion_authorized": False,
    }


def inspect_revisions(db, claim_id, *, observed_sources):
    """Pure comparison of currently observed source digests vs stored binds."""
    if not isinstance(claim_id, str) or not claim_id.startswith("garden.cycle."):
        raise ValueError("Not a Garden research-cycle claim")
    observed_sources = _validate_sources(observed_sources)
    rows = db.execute(
        """SELECT evidence_id,metadata_json FROM research_evidence
           WHERE evidence_id=?""",
        ("garden.cycle-evidence." + claim_id.split(".")[-1],),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("Missing original source-bound experiment evidence")
    original = json.loads(rows[0][1])["source_manifest"]
    # Verify ledger integrity before reading its lifecycle state.
    if not verify_integrity(db)["consistent"]:
        raise ValueError("Research ledger integrity failure")
    missing = sorted(set(original) - set(observed_sources))
    changed = sorted(k for k in original if k in observed_sources
                     and original[k] != observed_sources[k])
    unexpected = sorted(set(observed_sources) - set(original))
    last = db.execute(
        """SELECT event_id,assessment FROM research_events
           WHERE claim_id=? ORDER BY observed_at DESC,event_id DESC LIMIT 1""",
        (claim_id,),
    ).fetchone()
    if last is None:
        raise ValueError("Claim lacks a research assessment")
    return {
        "schema": SCHEMA, "claim_id": claim_id,
        "invalidated": bool(missing or changed or unexpected),
        "changed": changed, "missing": missing, "unexpected": unexpected,
        "original_manifest_sha256": digest(original),
        "observed_manifest_sha256": digest(observed_sources),
        "current_assessment": last[1],
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
    }


def reopen_on_revision(db, claim_id, *, observed_sources, evidence_uri, actor):
    """Append an evidence-backed invalidation event once per observed digest set.

    Evidence is a caller-supplied observation, not an independent source
    authenticity proof. Repeated observations are idempotent. No automatic
    re-validation or promotion follows a re-open.
    """
    report = inspect_revisions(db, claim_id, observed_sources=observed_sources)
    if not report["invalidated"]:
        return {**report, "event_appended": False}
    token = digest({"claim_id": claim_id,
                    "observed_manifest_sha256": report["observed_manifest_sha256"]})[:24]
    eid = "garden.revision-evidence." + token
    event_id = "garden.reopened." + token
    existing = db.execute("SELECT 1 FROM research_events WHERE event_id=?",
                          (event_id,)).fetchone()
    if existing:
        return {**report, "event_appended": False, "event_id": event_id}
    evidence(db, evidence_id=eid, kind="OBSERVATION", uri=evidence_uri,
             description="Observed source revision; research qualification reopened",
             content_sha256=report["observed_manifest_sha256"],
             metadata={"claim_id": claim_id, "changed": report["changed"],
                       "missing": report["missing"],
                       "unexpected": report["unexpected"],
                       "observed_sources": _validate_sources(observed_sources)})
    _event(db, claim_id=claim_id, event_id=event_id,
           assessment="INCONCLUSIVE",
           reason="Source dependency changed or disappeared; prior candidate requires replay",
           evidence_id=eid, actor=actor)
    if not verify_integrity(db)["consistent"]:
        raise ValueError("Ledger integrity check failed")
    return {**report, "event_appended": True, "event_id": event_id,
            "replay_required": True, "promotion_authorized": False}



def replay_after_revision(db, previous_claim_id, *, training, examples,
                          source, revised_source, workload, actor,
                          observation_uri, receipt_uri, trials=2,
                          max_proposals=24):
    """Re-run bounded research after observed source revision; retain ancestry.

    Inputs are source objects supplied by the caller. A reopened result cannot
    be admitted, and an ambiguous re-induction creates no new research claim.
    """
    from rct_garden_coevolution import run_investigation
    from store import digest as source_digest

    current = {
        "training": source_digest(training),
        "source": source_digest(source),
        "revised": source_digest(revised_source),
    }
    plan = inspect_revisions(db, previous_claim_id,
                             observed_sources=current)
    if not plan["invalidated"]:
        return {
            "schema": SCHEMA, "status": "NO_CHANGED_DEPENDENCIES",
            "previous_claim_id": previous_claim_id,
            "replayed": False, "promotion_authorized": False,
        }
    # Re-run the actual investigation. No externally supplied result may be
    # substituted for the model/grammar-derived experiment.
    result = run_investigation(
        training, examples, source, revised_source, workload,
        trials=trials, max_proposals=max_proposals)
    opened = reopen_on_revision(
        db, previous_claim_id, observed_sources=current,
        evidence_uri=observation_uri, actor=actor)
    if result["experiment"] is None:
        return {
            "schema": SCHEMA, "status": result["status"],
            "previous_claim_id": previous_claim_id,
            "replayed": True, "new_claim_id": None,
            "reopen_event_id": opened["event_id"],
            "next_step": "GENERATE_DISCRIMINATING_PROBE",
            "promotion_authorized": False,
            "qualityrag_admission": "INCONCLUSIVE",
        }
    fresh = register_cycle(
        db, result["experiment"], sources=current,
        evidence_uri=receipt_uri, actor=actor)
    if fresh["claim_id"] == previous_claim_id:
        raise ValueError("Replayed investigation did not create a new version")
    trace_id = "garden.replay-link." + digest({
        "old": previous_claim_id, "new": fresh["claim_id"]})[:24]
    # QUALIFIES expresses historical relation, not an unearned assertion of
    # semantic equivalence or replacement authority.
    link(db, link_id=trace_id, from_claim=fresh["claim_id"],
         to_claim=previous_claim_id, relation="QUALIFIES")
    if not verify_integrity(db)["consistent"]:
        raise ValueError("Replay ledger integrity failure")
    return {
        "schema": SCHEMA, "status": "REPLAYED_AS_UNVERIFIED_RESEARCH",
        "previous_claim_id": previous_claim_id,
        "new_claim_id": fresh["claim_id"],
        "reopen_event_id": opened["event_id"],
        "replayed": True, "new_experiment_sha256": fresh["experiment_sha256"],
        "qualityrag_admission": "INCONCLUSIVE",
        "promotion_authorized": False,
    }
