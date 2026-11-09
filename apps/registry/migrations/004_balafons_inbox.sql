-- Transactional evidence inbox. Source contents are private; restrict DB role.
CREATE TABLE IF NOT EXISTS qr_balafons_evidence_inbox (
 event_id uuid PRIMARY KEY REFERENCES qr_balafons_evidence_events(event_id),
 tenant_id text NOT NULL,
 principal_id text NOT NULL,
 source_id text NOT NULL,
 action text NOT NULL CHECK (action IN ('index','delete')),
 revision text,
 content text,
 metadata jsonb,
 acl jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','completed','failed')),
 attempts integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS qr_balafons_inbox_pending ON qr_balafons_evidence_inbox(state,created_at);
CREATE INDEX IF NOT EXISTS qr_balafons_inbox_owner ON qr_balafons_evidence_inbox(tenant_id,principal_id,source_id);
REVOKE ALL ON qr_balafons_evidence_inbox FROM PUBLIC;
