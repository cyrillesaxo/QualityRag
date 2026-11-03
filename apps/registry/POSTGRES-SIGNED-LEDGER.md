# PostgreSQL signed-promotion ledger (first production-oriented increment)

**Research lineage:** Cyrille Eloundou / https://apx.guide/

This backend makes the **signed policy promotion API** transactional across multiple registry processes. It does not replace the existing file-based development registry for legacy unsigned drafts and bindings, and it is not a complete production deployment.

## Database setup

Provision a PostgreSQL 16+ database using your infrastructure provider and configure TLS, backups, access control and a restricted application role. Apply the migration using a dedicated migration role:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f apps/registry/migrations/001_signed_postgres.sql
```

Start the signed-only registry:

```bash
export QUALITYRAG_REGISTRY_BACKEND=postgres
export DATABASE_URL='postgres://...'
export QUALITYRAG_AUTH_MODE=oidc
export QUALITYRAG_OIDC_ISSUER='https://identity.example/realms/governance'
export QUALITYRAG_OIDC_AUDIENCE='qualityrag-registry'
export QUALITYRAG_OIDC_JWKS_URI='https://identity.example/realms/governance/protocol/openid-connect/certs'
export QUALITYRAG_POLICY_KEYS_FILE='/etc/qualityrag/trusted-policy-keys.json'
npm --prefix apps/registry install
npm --prefix apps/registry start
```

**No database or cloud deployment is created by this PR.** The `DATABASE_URL` value above is a placeholder; actual credentials belong in a secrets manager.

## Signed lifecycle

```text
POST /v1/services (author)
         ↓
POST /v1/signed/promotions (author)
         ↓
POST /v1/signed/promotions/:service/:env/:seq/approve (different approver)
         ↓
POST /v1/signed/promotions/:service/:env/:seq/publish (third publisher)
         ↓
GET  /v1/signed/resolve/:service/:env (reader)
```

For each service/environment, every transition acquires a PostgreSQL `SELECT ... FOR UPDATE` lock on a single scope row. The transaction atomically updates status, the published sequence, and the governance event chain. Unique keys block duplicate staging of the same sequence. Publishing an older or identical sequence is rejected even if it was previously approved.

On concurrent publication of two **different** approved versions, the operations serialize; a later version can supersede an earlier version, but an earlier version cannot supersede a later version. On concurrent publication of the **same** version, only one can succeed. Failed transactions roll back their audit events.

The signed bundle is verified against pinned public keys at staging, approval, publication and resolution. The registry never requires or stores the signing private key.

## Deliberate boundaries

The PostgreSQL backend supports signed-only service registration, promotion, approval, publication, resolution and state listing. **Legacy unsigned draft/approve/bind/resolve APIs are unsupported in PostgreSQL mode** and fail explicitly. File-backed mode remains available for existing demonstrations.

The audit chain is now transactional, but its hashes are **not independently anchored**. Database superusers can rewrite history. Production requires externally anchored append-only audit export, permission-limited database roles, migrations and backups.

OIDC role separation is enforced by the existing registry server in OIDC mode. Single shared-token local mode is not suitable for real independent approvals.

Other missing production controls include deployment, authenticated browser login, distributed policy key revocation, transactional policy-sequence floors on application clients, independent evidence attestation, and disaster recovery validation.

## Tests

The `Studio and Registry` CI workflow starts a **real PostgreSQL 16** service and runs:

```bash
PG_TEST_DATABASE_URL=postgres://qualityrag:testpassword@127.0.0.1:5432/qualityrag_test \
  npm --prefix apps/registry test
```

This checks duplicate concurrent stage requests, competing simultaneous publishers, monotonic version enforcement, three-role separation, transactionally chained events and invalid signatures. The test database is disposable and must never be pointed at production.

**No request should silently downgrade from signed PostgreSQL policy retrieval to the legacy unsigned registry.**
