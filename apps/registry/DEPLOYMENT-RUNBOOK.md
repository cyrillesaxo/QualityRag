# QualityRag signed registry — PostgreSQL operations and recovery

**Status:** Deployment-ready building blocks, not a deployed production environment. Research lineage: Cyrille Eloundou / [APX](https://apx.guide/).

## Security prerequisites

Use a managed PostgreSQL 16+ instance with TLS, backups, restricted service and migration roles, and a tested restoration path. Give the registry a dedicated OIDC identity provider, issuer, audience and JWKS URI. Stage private Ed25519 keys **outside** the registry, then install only the approved public keys. Protect the database URL, issuer configuration and access tokens as deployment secrets.

The runtime requires `QUALITYRAG_REGISTRY_BACKEND=postgres` and `QUALITYRAG_AUTH_MODE=oidc` together. PostgreSQL mode refuses local single-token authentication and requires at least one trusted public signing key.

## Migration and startup

From the repository root:

```bash
npm --prefix apps/registry install

# Use a privileged migration role, not the runtime registry role:
DATABASE_URL="$MIGRATION_DATABASE_URL" node apps/registry/src/migrate.js

# Start the registry using a restricted runtime role:
QUALITYRAG_REGISTRY_BACKEND=postgres \
QUALITYRAG_AUTH_MODE=oidc \
QUALITYRAG_POLICY_KEYS_FILE=/run/secrets/qualityrag-policy-keys.json \
QUALITYRAG_OIDC_ISSUER="https://identity.example/realm" \
QUALITYRAG_OIDC_AUDIENCE="qualityrag-registry" \
QUALITYRAG_OIDC_JWKS_URI="https://identity.example/realm/certs" \
DATABASE_URL="$RUNTIME_DATABASE_URL" \
node apps/registry/src/server.js
```

**Migration safety:** `migrate.js` uses a PostgreSQL transaction and transaction-scoped advisory lock to serialize competing migration processes. It stores the SHA-256 of every applied migration and refuses to continue if an existing SQL file has changed. Schema changes must use a new numbered migration. Do not use `DROP SCHEMA` or automatically repair mismatched history.

**Startup safety:** the registry performs a database connectivity, applied-migration and governance-history check **before listening**. A mismatch or unavailable database blocks startup.

## Readiness and deployment probes

- `GET /health` is **liveness** only; a process can be live while its database is down.
- `GET /ready` is **readiness**; it checks migrations, database connectivity and governance audit continuity. It returns HTTP 503 without database details when checks fail.
- Keep the registry behind an HTTPS-capable reverse proxy or private load balancer. The process binds to `127.0.0.1` by default. In a trusted container network set `QUALITYRAG_BIND_HOST=0.0.0.0` and restrict ingress at the network layer.

Example container build:

```bash
docker build -t qualityrag-registry:local apps/registry
```

The image has a non-root process, includes the migration runner, and does **not** contain private policy signing keys. Run `node src/migrate.js` as a separate privileged migration job before starting the normal service.

## Recovery drill

1. Take a provider-managed database backup while the service is healthy. Record the backup timestamp and published sequence for every service/environment.
2. Restore into an **isolated database** with no public routes enabled. Provision the correct OIDC/JWKS and trusted public key set.
3. Run `migrate.js` against the isolated restoration. Any checksum mismatch is a hard stop; investigate, do not overwrite the migration ledger.
4. Start one isolated registry instance. Verify `/ready` returns 200 and cross-check the published sequence and signed bundle for a known service.
5. Attempt to promote a lower sequence in staging: it must be rejected. Verify the application-side minimum sequence floor is not reduced even if an older database snapshot is restored.
6. Test one signed-only consuming application against the restored environment. No unsigned endpoint fallback is permitted.
7. Promote production traffic only after independent checks of source integrity, audit anchoring (if configured), backups and expected policy versions.

**Important:** a database restore may roll back the server's published sequence. The application must maintain a **separate durable minimum accepted sequence**, or a restored older but valid signed policy could be accepted. This repository does not currently manage the consuming application's global sequence floor.

## Operational limits

The audit verification detects broken predecessor hashes, missing promotion transitions, incorrect recorded actors and scope-head inconsistencies. It does **not** provide tamper-proof audit evidence against database administrators, who can rewrite and rehash the database. External append-only audit anchoring is still required.

The readiness audit currently scans historical transitions for all scopes; measure and optimize its cost for large deployments before configuring high-frequency health checks. The Docker image is a deployment artifact, not an actual production deployment.

See [signed governance](SIGNED-PROMOTION.md), [OIDC configuration](OIDC-GOVERNANCE.md), and [transactional ledger](POSTGRES-SIGNED-LEDGER.md).
