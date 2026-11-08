-- Signed Balafons evidence replay ledger. Do not purge before retention policy permits.
CREATE TABLE IF NOT EXISTS qr_balafons_evidence_events (
 event_id uuid PRIMARY KEY,
 tenant_id text NOT NULL,
 principal_id text NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS qr_balafons_evidence_events_tenant ON qr_balafons_evidence_events(tenant_id,received_at);
REVOKE ALL ON qr_balafons_evidence_events FROM PUBLIC;
