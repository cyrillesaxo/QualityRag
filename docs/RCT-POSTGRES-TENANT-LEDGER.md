# PostgreSQL tenant-bound Semantic Store — integration candidate

This optional PostgreSQL backend adds database-enforced tenant isolation to the experimental Semantic Store. It is **not** a full migration of all existing SQLite query, APX receipt-import and semantic inference operations, and is **not** a production authorization system by itself.

## Architectural boundary

- Schema: `tools/semantic_store/pg/001_tenant_ledger.sql`
- Python runtime: `tools/semantic_store/pg_store.py` (`TenantPostgresStore`)
- Real database tests: `tools/semantic_store/tests/test_pg_store.py`
- CI: `.github/workflows/rct-postgres-ledger.yml` (PostgreSQL 16 service)

### Identity model

A trusted database administrator creates a dedicated PostgreSQL **LOGIN role** for each application tenant and binds it to a tenant UUID in `qr_private.tenant_role_bindings`. A trusted SECURITY DEFINER function looks up the tenant using **`session_user`**, not an application-provided tenant string, mutable request header, or writable session setting.

Application login roles only inherit `qr_runtime`. They are granted SELECT and INSERT on store tables and cannot read or alter the private tenant-role registry, change a different tenant's data, or update/delete any existing ledger record. All store tables use **FORCE ROW LEVEL SECURITY** with both select visibility and insert tenant checks. Every reference and edge uses composite tenant-qualified foreign keys.

The application **must not use a shared PostgreSQL LOGIN role for multiple tenants**; that would erase the very isolation property this design relies on. This architecture requires host identity-to-database-role provisioning, credential revocation/rotation and secure connection pool separation. Transaction-pooling proxies that reuse one authenticated database login across tenants invalidate the intended boundary.

### Database administrator migration

Install migration 001 using a privileged administrator on a dedicated DB. For example, with `psql`:

```bash
psql "$QR_PG_ADMIN_DSN" -v ON_ERROR_STOP=1 \
  -f tools/semantic_store/pg/001_tenant_ledger.sql
```

Use **database administrator** privileges for migration and tenant provisioning, never for runtime app connections.

A trusted provisioning service then performs a task equivalent to:

```sql
CREATE ROLE tenant_app_001 LOGIN PASSWORD 'USE_A_UNIQUE_ROTATED_SECRET';
GRANT qr_runtime TO tenant_app_001;
INSERT INTO qr_private.tenant_role_bindings(login_role, tenant_id)
VALUES ('tenant_app_001', '11111111-1111-4111-8111-111111111111');
```

The UUID above is illustrative, and the quoted password is **not** a production credential. For production, generate and rotate a secret through an authorized credential manager and revoke both login access and the role mapping when required.

### API surface

`TenantPostgresStore` provides:
- `add_source` and immutable source-revision checks;
- `add_object` with source-revision foreign keys and immutable payload digests;
- `add_edge` with cross-tenant-safe graph references;
- `object_version` that cannot read other tenants;
- `record_admission` that accepts only REFUSE / INCONCLUSIVE, never trusted ADMIT.
- `record_apx_receipt` preserving canonical HCR/RCOC outer result envelopes as `UNVERIFIED_EXTERNAL_RESULT`, never promoting them.
- `read_edges` and `pg_query.query_context_postgres` for bounded graph traversal with **both** database tenant RLS and mandatory per-object application authorization.

The backend reads tenant identity from its authenticated database connection, not from a `tenant_id` argument. It requires psycopg v3 and an autocommit connection, using explicit small transactions for insert operations.

### Tests and threat model

The CI suite creates two different PostgreSQL login roles and two distinct tenant UUIDs in a fresh PostgreSQL service, then proves:

1. The same object identity can exist in both tenants with different source/payload data and no cross-read.
2. Direct SQL cross-tenant inserts are rejected under RLS.
3. Changing a client-writable `app.tenant_id` setting does not change the authenticated tenant.
4. Cross-tenant graph references fail foreign-key validation.
5. Unbound login roles cannot initialize the runtime.
6. Private tenant-role registry, TRUNCATE, UPDATE, DELETE and unauthorized SET ROLE are inaccessible.
7. Even direct SQL cannot record an ADMIT receipt: PostgreSQL CHECK constraint rejects it.
8. SQL immutability triggers reject administrator direct UPDATE/DELETE unless the administrator intentionally modifies schema controls.

### Explicit limitations

- Highly privileged DB administrators, superusers and table owners with DDL can change schema or rewrite history. PostgreSQL cannot supply external immutability against its own superuser.
- RLS does not replace application-layer authentication, authorization, consent, field-level disclosure policy, or independent audit.
- Tenant-role provisioning, managed pooling, backup/restore isolation, encryption, log scrubbing and multi-region migration are not implemented.
- Bounded graph reads and HCR/RCOC receipt imports now have PostgreSQL equivalents, but complete behavioral parity with every SQLite feature and operational endpoint is not claimed. Do not expose this backend as a production-ready service.
- Source truth, semantic completeness, FF-RCT reconstruction and canonical APX parity are still not established by database constraints.
- This schema intentionally disallows ADMIT; production admission requires a separately authenticated governance/verifier design.

## Run

```bash
python -m pip install 'psycopg[binary]>=3.2,<3.3'
QR_PG_ADMIN_DSN='host=127.0.0.1 port=5432 dbname=qualityrag user=postgres password=postgres' \
  python -m unittest discover -s tools/semantic_store/tests -p test_pg_store.py -v
```

The example password is **only** for an isolated local CI PostgreSQL container. Never use it for real data.

## Remaining acceptance

- Wire customer-facing authentication and per-tenant DB role provisioning/rotation through a trusted service.
- Port bounded graph query, native APX receipts, and any intended production operations with full behavior parity tests.
- Run multi-tenant SQL injection, consent/privacy, pooling, backup and audit reviews before opening the service.
- Verify real canonical APX and native FF-RCT against independent authoritative datasets.
