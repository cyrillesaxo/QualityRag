-- Guided question replay protection. Additive; apply only through reviewed migration.
CREATE TABLE IF NOT EXISTS qr_guided_question_nonces (
 nonce_digest text PRIMARY KEY CHECK (nonce_digest ~ '^[a-f0-9]{64}$'),
 target_digest text NOT NULL CHECK (target_digest ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,
 consumed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- No source text, signatures, raw nonce, or learner identifiers retained.
-- No automatic deletion: retention requires a separate approved policy.
REVOKE ALL ON qr_guided_question_nonces FROM PUBLIC;
