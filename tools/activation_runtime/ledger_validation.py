"""Signed SQLite validation: receipt, replay guard and event share one transaction."""
from .authority import check_review
from .common import identity
from .gardener import ledger


def review_context(db, *, claim, evidence, scope, tenant, ledger_id, actor, event_id):
    identity(tenant);identity(ledger_id)
    if not isinstance(scope,str) or not 1<=len(scope)<=1000:
        raise ValueError("Explicit finite validation scope required")
    previous=db.execute("SELECT event_hash FROM research_events WHERE claim_id=? ORDER BY observed_at DESC,event_id DESC LIMIT 1",
                        (claim["claim_id"],)).fetchone()
    return {"schema":"qualityrag.sqlite-research-validation/v1",
            "ledger_id":ledger_id,"tenant":tenant,"event_id":event_id,"actor":actor,
            "claim_id":claim["claim_id"],"claim_record_sha256":claim["content_hash"],
            "previous_event_hash":previous[0] if previous else None,
            "dependencies":ledger.dependency_context(ledger.progress(db)["claims"],claim["claim_id"]),
            "evidence_record_sha256":{row["evidence_id"]:row["record_hash"] for row in evidence},
            "validation_scope":scope,"assessment":"VALIDATED"}


def validate_claim(db, *, event_id, claim_id, actor, evidence_ids, scope, signed_review,
                   reviewer_keys, author_public_key, as_of, tenant, ledger_id):
    if not isinstance(scope,str) or not 1<=len(scope)<=1000:
        raise ValueError("Explicit finite validation scope required")
    main=next((row for row in db.execute("PRAGMA database_list") if row[1]=="main"),None)
    if main is None or not main[2]:raise ValueError("Durable SQLite ledger required")
    def verifier(claim,evidence):
        if not ledger.verify_integrity(db)["consistent"]:raise ValueError("Research evidence integrity failure")
        context=review_context(db,claim=claim,evidence=evidence,scope=scope,tenant=tenant,
                               ledger_id=ledger_id,actor=actor,event_id=event_id)
        checked=check_review(signed_review,reviewer_keys,context=context,
                             author_public_key=author_public_key,as_of=as_of)
        if checked["reviewer"]!=actor:
            raise PermissionError("Event actor must match the signed reviewer")
        inserted=db.execute(
            "INSERT INTO research_validation_receipts "
            "(service,tenant,nonce,event_id,reviewer,context_sha256,review_envelope) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(service,tenant,nonce) DO NOTHING RETURNING nonce",
            ("research-validation",tenant,checked["nonce"],event_id,actor,
             checked["context_sha256"],ledger.canon(signed_review))).fetchone()
        if inserted is None:raise PermissionError("Review replay")
        return True
    return ledger.assess(db,event_id=event_id,claim_id=claim_id,assessment="VALIDATED",
        reason="Independent signed review limited to: "+scope,actor=actor,evidence_ids=evidence_ids,
        at=as_of,verify_validation=verifier)
