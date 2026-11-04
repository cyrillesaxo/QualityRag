"""Signed, scope-bounded integration with the canonical Research Ledger."""
from .authority import verify_review
from .gardener import ledger


def validate_claim(db,*,event_id,claim_id,actor,evidence_ids,scope,signed_review,
                   reviewer_keys,author_public_key,as_of,nonce_store,tenant):
    if not isinstance(scope,str) or not 1<=len(scope)<=1000:raise ValueError("Explicit finite validation scope required")
    def verifier(claim,evidence):
        if not ledger.verify_integrity(db)["consistent"]:raise ValueError("Research evidence integrity failure")
        context={"claim_id":claim["claim_id"],"claim_record_sha256":claim["content_hash"],
                 "evidence_record_sha256":{row["evidence_id"]:row["record_hash"] for row in evidence},
                 "validation_scope":scope,"assessment":"VALIDATED"}
        verify_review(signed_review,reviewer_keys,context=context,author_public_key=author_public_key,
                      as_of=as_of,nonce_store=nonce_store,tenant=tenant)
        return True
    return ledger.assess(db,event_id=event_id,claim_id=claim_id,assessment="VALIDATED",
        reason="Independent signed review limited to: "+scope,actor=actor,evidence_ids=evidence_ids,
        at=as_of,verify_validation=verifier)
