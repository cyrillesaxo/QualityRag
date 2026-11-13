-- One-time OAuth state and PKCE verifier for callbacks on any Registry replica.
-- The selector is a keyed digest of the random state; PKCE and owner are AES-GCM.
CREATE TABLE IF NOT EXISTS qr_drive_oauth_pending (
 state_key char(64) PRIMARY KEY,
 encrypted_pending jsonb NOT NULL CHECK (jsonb_typeof(encrypted_pending)='object'),
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS qr_drive_oauth_pending_expires
 ON qr_drive_oauth_pending(expires_at);
REVOKE ALL ON qr_drive_oauth_pending FROM PUBLIC;
