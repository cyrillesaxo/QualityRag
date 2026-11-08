-- QualityRAG cloud connector metadata and OAuth state; apply via reviewed migration.
CREATE TABLE IF NOT EXISTS qr_connector_oauth_states (
 state_hash text PRIMARY KEY CHECK (length(state_hash) = 43),
 tenant_id text NOT NULL,
 principal_id text NOT NULL,
 provider text NOT NULL CHECK (provider IN ('google','microsoft','dropbox','box')),
 code_verifier text NOT NULL,
 expires_at timestamptz NOT NULL,
 consumed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS qr_connector_oauth_expiry ON qr_connector_oauth_states(expires_at);
CREATE TABLE IF NOT EXISTS qr_connector_credentials (
 connection_id text PRIMARY KEY,
 tenant_id text NOT NULL,
 principal_id text NOT NULL,
 provider text NOT NULL CHECK (provider IN ('google','microsoft','dropbox','box')),
 display_name text NOT NULL DEFAULT '',
 encrypted_record jsonb NOT NULL,
 granted_scopes text[] NOT NULL DEFAULT '{}',
 status text NOT NULL DEFAULT 'connected' CHECK (status IN ('connected','expired','error','revoked')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id,tenant_id,principal_id,provider)
);
CREATE INDEX IF NOT EXISTS qr_connector_credentials_owner ON qr_connector_credentials(tenant_id,principal_id);
REVOKE ALL ON qr_connector_oauth_states,qr_connector_credentials FROM PUBLIC;
