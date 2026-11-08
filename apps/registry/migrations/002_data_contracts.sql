-- QualityRag data contracts (ADR-0002): signed, staged, approved, published, hash-chained audit.
CREATE TABLE IF NOT EXISTS qr_contract_heads (
  contract_id text PRIMARY KEY CHECK (contract_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
  tenant text NOT NULL CHECK (tenant ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
  kind text NOT NULL CHECK (kind IN ('source','destination')),
  published_sequence bigint NOT NULL DEFAULT 0 CHECK (published_sequence >= 0),
  published_signature text,
  published_sha256 text,
  last_hash text NOT NULL DEFAULT repeat('0',64)
);
CREATE TABLE IF NOT EXISTS qr_contract_promotions (
  contract_id text NOT NULL REFERENCES qr_contract_heads(contract_id),
  sequence bigint NOT NULL CHECK (sequence > 0),
  status text NOT NULL CHECK (status IN ('STAGED','APPROVED','PUBLISHED')),
  envelope jsonb NOT NULL,
  signature text NOT NULL,
  sha256 text NOT NULL,
  key_id text NOT NULL,
  staged_by text NOT NULL,
  approved_by text,
  published_by text,
  staged_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  published_at timestamptz,
  PRIMARY KEY(contract_id,sequence),
  CHECK ((status = 'STAGED' AND approved_by IS NULL AND published_by IS NULL)
    OR (status = 'APPROVED' AND approved_by IS NOT NULL AND published_by IS NULL)
    OR (status = 'PUBLISHED' AND approved_by IS NOT NULL AND published_by IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS qr_contract_events (
  event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  contract_id text NOT NULL REFERENCES qr_contract_heads(contract_id),
  sequence bigint NOT NULL,
  actor text NOT NULL,
  action text NOT NULL CHECK (action IN ('STAGED','APPROVED','PUBLISHED')),
  previous_hash text NOT NULL,
  event_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS qr_contract_heads_tenant ON qr_contract_heads(tenant);
