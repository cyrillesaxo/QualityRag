-- QualityRag signed-only PostgreSQL registry v1. Run once with a migration role.
CREATE TABLE IF NOT EXISTS qr_services (
  service_id text PRIMARY KEY CHECK (service_id ~ '^[A-Za-z0-9._-]+$'),
  display_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- A lock row is created on stage; all transitions for this service/environment
-- acquire SELECT ... FOR UPDATE on the same row.
CREATE TABLE IF NOT EXISTS qr_scopes (
  service_id text NOT NULL REFERENCES qr_services(service_id),
  environment text NOT NULL CHECK (environment ~ '^[A-Za-z0-9._-]+$'),
  published_sequence bigint NOT NULL DEFAULT 0 CHECK (published_sequence >= 0),
  published_signature text,
  published_ir_sha256 text,
  PRIMARY KEY(service_id,environment)
);
CREATE TABLE IF NOT EXISTS qr_signed_promotions (
  service_id text NOT NULL,
  environment text NOT NULL,
  sequence bigint NOT NULL CHECK (sequence > 0),
  status text NOT NULL CHECK (status IN ('STAGED','APPROVED','PUBLISHED')),
  bundle jsonb NOT NULL,
  signature text NOT NULL,
  ir_sha256 text NOT NULL,
  key_id text NOT NULL,
  staged_by text NOT NULL,
  approved_by text,
  published_by text,
  staged_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  published_at timestamptz,
  PRIMARY KEY(service_id,environment,sequence),
  FOREIGN KEY(service_id,environment) REFERENCES qr_scopes(service_id,environment),
  CHECK ((status = 'STAGED' AND approved_by IS NULL AND published_by IS NULL)
    OR (status = 'APPROVED' AND approved_by IS NOT NULL AND published_by IS NULL)
    OR (status = 'PUBLISHED' AND approved_by IS NOT NULL AND published_by IS NOT NULL))
);
-- Transactional append-only audit. Hash is for accidental/tamper detection,
-- not an external anchor or cryptographic attestation of database operators.
CREATE TABLE IF NOT EXISTS qr_governance_events (
  event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  service_id text NOT NULL,
  environment text NOT NULL,
  sequence bigint NOT NULL,
  actor text NOT NULL,
  action text NOT NULL CHECK (action IN ('STAGED','APPROVED','PUBLISHED')),
  previous_hash text NOT NULL,
  event_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(service_id,environment) REFERENCES qr_scopes(service_id,environment)
);
CREATE TABLE IF NOT EXISTS qr_governance_heads (
  service_id text NOT NULL,
  environment text NOT NULL,
  last_hash text NOT NULL DEFAULT repeat('0',64),
  PRIMARY KEY(service_id,environment),
  FOREIGN KEY(service_id,environment) REFERENCES qr_scopes(service_id,environment)
);
CREATE INDEX IF NOT EXISTS qr_signed_promotions_lookup ON qr_signed_promotions(service_id,environment,status);
