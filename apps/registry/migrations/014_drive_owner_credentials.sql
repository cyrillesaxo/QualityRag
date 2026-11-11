-- US-068 per-owner Google credential state, isolated from governance cursor data.
-- No plaintext OAuth tokens, emails, folder names or owner IDs in PostgreSQL.
CREATE TABLE IF NOT EXISTS qr_drive_owner_credentials (
 owner_key char(64) PRIMARY KEY,
 revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
 credential_envelope jsonb,
 disconnected boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((disconnected AND credential_envelope IS NULL) OR
        (NOT disconnected AND jsonb_typeof(credential_envelope) = 'object'))
);
REVOKE ALL ON qr_drive_owner_credentials FROM PUBLIC;
-- The application service role must be granted privileges explicitly by
-- a reviewed deployment migration. No grant to public/anonymous roles.
