"""Attach a joint grammar/activation research receipt to the EXISTING ledger.

No duplicate event store, no semantic promotion, no production authorization.
"""
from __future__ import annotations
from pathlib import Path
import sys

from rct_joint_optimizer import SCHEMA
from store import digest

_LEDGER = Path(__file__).resolve().parents[1] / "research_ledger"
if str(_LEDGER) not in sys.path:
    sys.path.insert(0, str(_LEDGER))

from ledger import claim, evidence, assess, verify_integrity  # noqa: E402


def append_joint_research(db, receipt: dict, *, evidence_uri: str,
                          actor: str, project: str = "QualityRag") -> dict:
    """Record immutable research provenance; a second append is a duplicate.

    A caller must supply a retrievable external URI. We do not create or
    authenticate the artifact described by that URI.
    """
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError("Wrong joint experiment schema")
    body = dict(receipt)
    h = body.pop("fingerprint", None)
    if h != digest(body) or not isinstance(h, str):
        raise ValueError("Experiment receipt fingerprint mismatch")
    if (receipt.get("qualityrag_admission") != "INCONCLUSIVE" or
            receipt.get("can_generate") is not False or
            receipt.get("champion") is not None or
            receipt.get("promotion_authorized") is not False or
            len(receipt.get("results", [])) != 6 or
            not all(r.get("qualityrag_admission") == "INCONCLUSIVE"
                    and r.get("can_generate") is False
                    for r in receipt["results"])):
        raise ValueError("Unsafe or incomplete experiment receipt")
    identifier = h[:24]
    claim_id = "garden.joint." + identifier
    evidence_id = "garden.measure." + identifier
    event_id = "garden.inconclusive." + identifier
    # Reuse exact ledger claim/evidence/assessment contract, retaining all
    # existing trigger, hash-chain and admission limitations.
    claim(db, claim_id=claim_id, project=project, kind="EXPERIMENT",
          statement="A bounded grammar/activation comparison was executed; "
                    "finite structural outcomes do not certify semantic superiority.")
    evidence(db, evidence_id=evidence_id, kind="MEASUREMENT",
             uri=evidence_uri, description=(
                 "Versioned joint grammar/activation candidate comparison; "
                 "local runtime and storage proxies, not independent validation."),
             content_sha256=h,
             metadata={"schema": SCHEMA, "receipt_fingerprint": h,
                       "source_sha256": receipt["source_sha256"],
                       "updated_source_sha256": receipt["updated_source_sha256"],
                       "training_sha256": receipt["training_sha256"],
                       "candidate_count": len(receipt["results"])})
    assess(db, event_id=event_id, claim_id=claim_id, assessment="INCONCLUSIVE",
           reason="Structural reconstruction verified; independent RCT/FF-RCT, "
                  "D15, source authority and production benchmarks absent.",
           actor=actor, evidence_ids=[evidence_id])
    integrity = verify_integrity(db)
    if not integrity["consistent"]:
        raise ValueError("Research ledger integrity failed")
    return {"claim_id": claim_id, "evidence_id": evidence_id,
            "event_id": event_id, "status": "INCONCLUSIVE",
            "receipt_fingerprint": h, "ledger_integrity": "CONSISTENT"}
