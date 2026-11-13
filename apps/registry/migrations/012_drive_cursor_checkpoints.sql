-- US-068: durable, owner-scoped CAS checkpoint on the existing Registry PostgreSQL.
-- Stores AES-GCM envelopes only; owner_key and binding are keyed digests, not identities.
CREATE TABLE IF NOT EXISTS qr_drive_cursor_checkpoints (
 owner_key char(64) PRIMARY KEY,
 generation char(64) NOT NULL,
 binding_digest char(64) NOT NULL,
 cursor_version bigint NOT NULL DEFAULT 0 CHECK (cursor_version >= 0),
 encrypted_cursor jsonb,
 stale boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (encrypted_cursor IS NULL OR jsonb_typeof(encrypted_cursor) = 'object')
);
REVOKE ALL ON qr_drive_cursor_checkpoints FROM PUBLIC;
