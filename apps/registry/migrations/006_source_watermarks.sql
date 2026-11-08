-- High-water mark survives deletes and prevents stale event resurrection.
CREATE TABLE IF NOT EXISTS qr_source_watermarks (
 tenant_id text NOT NULL,principal_id text NOT NULL,source_id text NOT NULL,
 source_sequence bigint NOT NULL CHECK(source_sequence>=0),
 last_event_id uuid NOT NULL,deleted boolean NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,source_id),
 CHECK(tenant_id='balafons:'||principal_id),
 CHECK(left(source_id,length(tenant_id)+1)=tenant_id||':')
);
ALTER TABLE qr_balafons_evidence_inbox ADD COLUMN IF NOT EXISTS source_sequence bigint;
REVOKE ALL ON qr_source_watermarks FROM PUBLIC;
