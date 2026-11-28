-- Append-only receipt revocations. No production grants are assigned here.
CREATE TABLE qr_guided_question_receipt_revocations (
 receipt_digest text PRIMARY KEY REFERENCES qr_guided_question_receipts(receipt_digest),
 reason text NOT NULL CHECK(reason IN ('OWNER_WITHDRAWN','REVIEW_DISPUTED','CUSTODY_DISPUTED')),
 actor_binding text NOT NULL CHECK(actor_binding ~ '^[a-f0-9]{64}$'),
 revoked_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON qr_guided_question_receipt_revocations FROM PUBLIC;
