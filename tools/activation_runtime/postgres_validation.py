"""Signed PostgreSQL validation with transactionally stored review and replay guard.

Host configuration supplies the connection and trust maps. Database identity and
tenant are part of the signed context; neither is inferred from source text.
This is scope-bounded reviewer approval, not automatic scientific validation.
"""
from .authority import check_review
from .common import identity
from .gardener import ledger  # Initializes the canonical ledger import path.
import postgres


def review_context(conn, *, claim, evidence, scope, tenant, ledger_id, actor, event_id):
    identity(tenant)
    identity(ledger_id)
    if not isinstance(scope,str) or not 1<=len(scope)<=1000:
        raise ValueError("Explicit finite validation scope required")
    database=conn.execute("SELECT current_database()").fetchone()[0]
    previous=conn.execute("SELECT event_hash FROM research.assessment_events WHERE claim_id=%s ORDER BY observed_at DESC,event_id DESC LIMIT 1",
                          (claim["claim_id"],)).fetchone()
    return {"schema":"qualityrag.postgres-research-validation/v1",
            "database":database,"ledger_id":ledger_id,"tenant":tenant,"event_id":event_id,"actor":actor,
            "claim_id":claim["claim_id"],"claim_record_sha256":claim["content_hash"],
            "previous_event_hash":previous[0] if previous else None,
            "dependencies":ledger.dependency_context(postgres.progress(conn)["claims"],claim["claim_id"]),
            "evidence_record_sha256":{row["evidence_id"]:row["record_hash"] for row in evidence},
            "validation_scope":scope,"assessment":"VALIDATED"}


def validate_claim(conn, *, event_id, claim_id, actor, evidence_ids, scope,
                   signed_review, reviewer_keys, author_public_key, as_of, tenant, ledger_id):
    if not isinstance(scope,str) or not 1<=len(scope)<=1000:
        raise ValueError("Explicit finite validation scope required")
    # This verifier is installed by trusted application code, never from an API body.
    def verifier(claim,evidence):
        if not postgres.verify_integrity(conn)["consistent"]:
            raise ValueError("Research evidence integrity failure")
        context=review_context(conn,claim=claim,evidence=evidence,scope=scope,
                               tenant=tenant,ledger_id=ledger_id,actor=actor,event_id=event_id)
        checked=check_review(signed_review,reviewer_keys,context=context,
                             author_public_key=author_public_key,as_of=as_of)
        if checked["reviewer"]!=actor:
            raise PermissionError("Event actor must match the signed reviewer")
        inserted=conn.execute(
            "INSERT INTO research.validation_receipts "
            "(service,tenant,nonce,event_id,reviewer,context_sha256,review_envelope) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) "
            "ON CONFLICT (service,tenant,nonce) DO NOTHING RETURNING nonce",
            ("research-validation",tenant,checked["nonce"],event_id,actor,
             checked["context_sha256"],ledger.canon(signed_review))).fetchone()
        if inserted is None:raise PermissionError("Review replay")
        return True
    return postgres.assess(conn,event_id=event_id,claim_id=claim_id,
        assessment="VALIDATED",reason="Independent signed review limited to: "+scope,
        actor=actor,evidence_ids=evidence_ids,at=as_of,verify_validation=verifier)
