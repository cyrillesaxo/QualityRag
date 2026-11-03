-- QualityRag isolated PostgreSQL candidate ledger v0.1.
-- Requires a trusted database administrator to install. Every application
-- login role is bound to exactly one tenant by this privileged registry.
-- NEVER use an application-provided tenant header or writable session GUC
-- as the isolation authority. Policy decisions remain INCONCLUSIVE/REFUSE.
BEGIN;

CREATE SCHEMA IF NOT EXISTS qr_private;
CREATE SCHEMA IF NOT EXISTS qr_store;
REVOKE ALL ON SCHEMA qr_private FROM PUBLIC;
REVOKE ALL ON SCHEMA qr_store FROM PUBLIC;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qr_runtime') THEN
    CREATE ROLE qr_runtime NOLOGIN;
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS qr_private.tenant_role_bindings (
  login_role name PRIMARY KEY,
  tenant_id uuid NOT NULL
);
REVOKE ALL ON qr_private.tenant_role_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION qr_private.authenticated_tenant()
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, qr_private
AS $$
  SELECT tenant_id FROM qr_private.tenant_role_bindings
  WHERE login_role = session_user::name
$$;
REVOKE ALL ON FUNCTION qr_private.authenticated_tenant() FROM PUBLIC;
GRANT USAGE ON SCHEMA qr_private TO qr_runtime;
GRANT EXECUTE ON FUNCTION qr_private.authenticated_tenant() TO qr_runtime;

CREATE TABLE IF NOT EXISTS qr_store.source_versions (
 tenant_id uuid NOT NULL,
 source_id text NOT NULL,
 revision text NOT NULL,
 source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
 metadata_json jsonb NOT NULL,
 PRIMARY KEY(tenant_id, source_id, revision)
);
CREATE TABLE IF NOT EXISTS qr_store.semantic_versions (
 tenant_id uuid NOT NULL,
 object_id text NOT NULL,
 revision text NOT NULL,
 source_id text NOT NULL,
 source_revision text NOT NULL,
 kind text NOT NULL CHECK(length(kind)>0),
 payload_json jsonb NOT NULL,
 payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(tenant_id, object_id, revision),
 FOREIGN KEY(tenant_id, source_id, source_revision)
   REFERENCES qr_store.source_versions(tenant_id, source_id, revision)
);
CREATE TABLE IF NOT EXISTS qr_store.semantic_edges (
 tenant_id uuid NOT NULL,
 edge_id text NOT NULL,
 layer text NOT NULL CHECK(layer IN ('KNOWLEDGE','WITNESS','REGIME')),
 from_id text NOT NULL,
 from_revision text NOT NULL,
 to_id text NOT NULL,
 to_revision text NOT NULL,
 relation text NOT NULL,
 properties_json jsonb NOT NULL,
 PRIMARY KEY(tenant_id, edge_id),
 FOREIGN KEY(tenant_id, from_id, from_revision)
   REFERENCES qr_store.semantic_versions(tenant_id, object_id, revision),
 FOREIGN KEY(tenant_id, to_id, to_revision)
   REFERENCES qr_store.semantic_versions(tenant_id, object_id, revision)
);
CREATE TABLE IF NOT EXISTS qr_store.apx_receipts (
 tenant_id uuid NOT NULL,
 receipt_sha256 text NOT NULL CHECK(receipt_sha256 ~ '^[0-9a-f]{64}$'),
 object_id text NOT NULL,
 revision text NOT NULL,
 engine text NOT NULL CHECK(engine IN ('HCR','RCOC')),
 schema_id text NOT NULL,
 source_digests_json jsonb NOT NULL,
 receipt_json jsonb NOT NULL,
 verification text NOT NULL CHECK(verification='UNVERIFIED_EXTERNAL_RESULT'),
 PRIMARY KEY(tenant_id, receipt_sha256),
 FOREIGN KEY(tenant_id, object_id, revision)
   REFERENCES qr_store.semantic_versions(tenant_id, object_id, revision)
);
CREATE TABLE IF NOT EXISTS qr_store.admission_receipts (
 tenant_id uuid NOT NULL,
 receipt_hash text NOT NULL CHECK(receipt_hash ~ '^[0-9a-f]{64}$'),
 object_id text NOT NULL,
 revision text NOT NULL,
 packspec_digest text NOT NULL,
 verdict text NOT NULL CHECK(verdict IN ('REFUSE','INCONCLUSIVE')),
 reason text NOT NULL,
 checks_json jsonb NOT NULL,
 PRIMARY KEY(tenant_id, receipt_hash),
 FOREIGN KEY(tenant_id, object_id, revision)
   REFERENCES qr_store.semantic_versions(tenant_id, object_id, revision)
);
CREATE INDEX IF NOT EXISTS semantic_edges_from_idx
  ON qr_store.semantic_edges(tenant_id,from_id,from_revision);
CREATE INDEX IF NOT EXISTS semantic_edges_to_idx
  ON qr_store.semantic_edges(tenant_id,to_id,to_revision);

CREATE OR REPLACE FUNCTION qr_private.reject_ledger_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
  RAISE EXCEPTION 'immutable semantic ledger';
END;
$$;
REVOKE ALL ON FUNCTION qr_private.reject_ledger_mutation() FROM PUBLIC;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'source_versions','semantic_versions','semantic_edges',
    'apx_receipts','admission_receipts'
  ] LOOP
    EXECUTE format('ALTER TABLE qr_store.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE qr_store.%I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_bound ON qr_store.%I',t);
    EXECUTE format(
      'CREATE POLICY tenant_bound ON qr_store.%I FOR ALL TO qr_runtime '
      || 'USING (tenant_id=qr_private.authenticated_tenant()) '
      || 'WITH CHECK (tenant_id=qr_private.authenticated_tenant())',t);
    EXECUTE format('DROP TRIGGER IF EXISTS immutable_ledger ON qr_store.%I',t);
    EXECUTE format(
      'CREATE TRIGGER immutable_ledger BEFORE UPDATE OR DELETE ON qr_store.%I '
      || 'FOR EACH ROW EXECUTE FUNCTION qr_private.reject_ledger_mutation()',t);
    EXECUTE format('REVOKE ALL ON qr_store.%I FROM PUBLIC',t);
    EXECUTE format('GRANT SELECT,INSERT ON qr_store.%I TO qr_runtime',t);
  END LOOP;
END
$$;
GRANT USAGE ON SCHEMA qr_store TO qr_runtime;

COMMIT;
