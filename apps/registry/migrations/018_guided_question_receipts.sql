-- Historical decisions, atomically persisted with one-time nonce consumption.
CREATE TABLE qr_guided_question_receipts (
 receipt_digest text PRIMARY KEY CHECK (receipt_digest ~ '^[a-f0-9]{64}$'),
 nonce_digest text NOT NULL UNIQUE REFERENCES qr_guided_question_nonces(nonce_digest),
 owner_binding text NOT NULL CHECK (owner_binding ~ '^[a-f0-9]{64}$'),
 service_id text NOT NULL,
 environment text NOT NULL,
 policy_digest text NOT NULL CHECK (policy_digest ~ '^[a-f0-9]{64}$'),
 target_digest text NOT NULL CHECK (target_digest ~ '^[a-f0-9]{64}$'),
 reviewer_id text NOT NULL,
 grant_version bigint NOT NULL CHECK(grant_version>0),
 key_digest text NOT NULL CHECK (key_digest ~ '^[a-f0-9]{64}$'),
 verdict text NOT NULL CHECK (verdict IN ('ADMIT','REFUSE','INCONCLUSIVE')),
 expires_at timestamptz NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON qr_guided_question_receipts FROM PUBLIC;
-- Historical records are not reusable release permits. No automatic pruning.
