"""Portable PostgreSQL 16+ foundation for the QualityRag research evidence ledger.

No Supabase service or proprietary extension is required. Migration is
create-only and does not modify existing application tables. Graph edges are
first-class relational records; vector storage is optional and separately
enabled with CREATE EXTENSION vector if available.
"""
CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.claims (
  claim_id text PRIMARY KEY,
  project text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('HYPOTHESIS','CAPABILITY','EXPERIMENT','DECISION')),
  statement text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  content_hash char(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS research.evidence (
  evidence_id text PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('CODE_COMMIT','CI_RUN','TEST_RESULT','MEASUREMENT','REVIEW','SOURCE_DOCUMENT','DEPLOYMENT','OBSERVATION')),
  uri text NOT NULL,
  description text NOT NULL,
  content_sha256 char(64),
  observed_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  record_hash char(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS research.assessment_events (
  event_id text PRIMARY KEY,
  claim_id text NOT NULL REFERENCES research.claims(claim_id),
  assessment text NOT NULL CHECK(assessment IN ('UNVERIFIED','IMPLEMENTED','TESTED','VALIDATED','REFUTED','SUPERSEDED','INCONCLUSIVE')),
  reason text NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  previous_event_hash char(64),
  event_hash char(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS research_assessments_by_claim ON research.assessment_events(claim_id,observed_at,event_id);
CREATE TABLE IF NOT EXISTS research.claim_links (
  link_id text PRIMARY KEY,
  from_claim text NOT NULL REFERENCES research.claims(claim_id),
  to_claim text NOT NULL REFERENCES research.claims(claim_id),
  relation text NOT NULL CHECK(relation IN ('SUPPORTS','CHALLENGES','DEPENDS_ON','SUPERSEDES','QUALIFIES')),
  created_at timestamptz NOT NULL DEFAULT now(),
  link_hash char(64) NOT NULL,
  CHECK(from_claim<>to_claim)
);
CREATE INDEX IF NOT EXISTS research_claims_by_project ON research.claims(project);

-- PostgreSQL protection against accidental mutations; owners or privileged
-- DBAs can still change schema/functions. Production requires a dedicated
-- restricted writer service role, audit logs, backups and external attestation.
CREATE OR REPLACE FUNCTION research.reject_existing_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Research ledger is append-only';
END;
$$;
DO $$
DECLARE tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['claims','evidence','assessment_events','claim_links'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='research' AND c.relname=tbl
        AND t.tgname='reject_'||tbl||'_mutation') THEN
      EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON research.%I
                      FOR EACH ROW EXECUTE FUNCTION research.reject_existing_mutation()',
                     'reject_'||tbl||'_mutation',tbl);
    END IF;
  END LOOP;
END $$;

CREATE OR REPLACE VIEW research.current_claim_status AS
SELECT c.claim_id,c.project,c.kind,c.statement,c.created_at,
       COALESCE(e.assessment,'UNVERIFIED') AS status,e.reason,
       e.observed_at AS latest_assessment_at
FROM research.claims c
LEFT JOIN LATERAL(
   SELECT assessment,reason,observed_at
   FROM research.assessment_events e
   WHERE e.claim_id=c.claim_id ORDER BY e.observed_at DESC,e.event_id DESC LIMIT 1
) e ON true;

-- Opt-in only, after confirming pgvector is supported by the host:
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE TABLE research.semantic_embeddings(
--   claim_id text REFERENCES research.claims(claim_id),
--   model_id text NOT NULL, source_revision text NOT NULL,
--   embedding vector(768) NOT NULL,
--   PRIMARY KEY(claim_id,model_id,source_revision)
-- );
-- Dimension must match the chosen embedding model. Never mix model versions.
