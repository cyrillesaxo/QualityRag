-- Durable tenant-partitioned lexical retrieval index.
CREATE TABLE IF NOT EXISTS qr_source_chunks (
 tenant_id text NOT NULL,
 principal_id text NOT NULL,
 source_id text NOT NULL,
 revision text NOT NULL,
 ordinal integer NOT NULL CHECK (ordinal >= 0),
 start_offset integer NOT NULL CHECK (start_offset >= 0),
 end_offset integer NOT NULL CHECK (end_offset > start_offset),
 content text NOT NULL,
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
 lexemes tsvector GENERATED ALWAYS AS (to_tsvector('simple',content)) STORED,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,source_id,ordinal),
 CHECK (tenant_id = 'balafons:' || principal_id),
 CHECK (left(source_id,length(tenant_id)+1) = tenant_id || ':')
);
CREATE INDEX IF NOT EXISTS qr_source_chunks_lexemes ON qr_source_chunks USING GIN (lexemes);
CREATE INDEX IF NOT EXISTS qr_source_chunks_owner ON qr_source_chunks (tenant_id,principal_id,source_id);
REVOKE ALL ON qr_source_chunks FROM PUBLIC;
