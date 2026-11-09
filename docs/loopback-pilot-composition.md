# QualityRAG loopback pilot composition (not a production deployment)

The default `npm --prefix apps/registry start` continues to run without Google Drive, encrypted indexing or signed-review trust material. The optional startup composition is **deliberately restricted to a single local process bound to loopback**. No customer pilot has been executed and no independent security signoff has been issued.

## Mandatory operator preflight

Before configuring credentials, obtain written customer authorization, approve the selected folder and non-sensitive documents, validate OAuth app/consent requirements, and review token retention, deletion, and network transport. The selected Google OAuth scope is `drive.readonly`; a real installation may require Google verification depending on deployment and users.

Provision a private absolute data directory (mode `0700`) and an independently trusted public-key file (mode `0600`) containing distinct Ed25519 keys for custodian and meaning reviewer. **Do not place signing private keys in Registry or Studio**. Use an independent secrets manager for two distinct 32-byte base64 encryption keys. Never commit keys or OAuth credentials; do not put them in documentation, CI logs or evidence artifacts.

This prototype uses file-backed encrypted Google tokens/index and a local integrity-chain evidence ledger; it is **not** a multi-instance transactional or externally anchored audit system. Use one process only, and do not expose it directly on a public interface.

## Configuration contract

The operator sets these values through a protected process environment (no sample credentials):

| Variable | Constraint |
| --- | --- |
| `QUALITYRAG_PILOT_MODE` | Must be exactly `true`; otherwise components remain disabled |
| `QUALITYRAG_PILOT_APPROVED_NETWORK` | Must be exactly `true`, **after** an independent network/security review; this flag itself is not proof |
| `QUALITYRAG_AUTH_MODE` | `oidc` |
| `QUALITYRAG_BIND_HOST` | `127.0.0.1` or `::1` (no public bind) |
| `QUALITYRAG_OIDC_ISSUER`, `QUALITYRAG_OIDC_AUDIENCE`, `QUALITYRAG_OIDC_JWKS_URI` | Trusted identity provider configuration; only signed tokens with exact service-scopes work |
| `QUALITYRAG_PILOT_DATA_DIR` | Absolute, existing, private `0700` directory |
| `QUALITYRAG_PROTECTED_DRIVE_SERVICES` | Explicit comma-separated `service@environment` allowlist |
| `QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE` | Absolute private `0600` file with two distinct trusted signer public keys |
| `QUALITYRAG_DRIVE_ENCRYPTION_KEY`, `QUALITYRAG_DRIVE_INDEX_KEY` | Separate random 32-byte keys, base64 encoded |
| `QUALITYRAG_GOOGLE_CLIENT_ID`, `QUALITYRAG_GOOGLE_CLIENT_SECRET` | Operator-approved Google OAuth client credentials |
| `QUALITYRAG_GOOGLE_REDIRECT_URI` | HTTPS public callback path or explicit local test redirect ending in `/v1/drives/google/callback` |
| `QUALITYRAG_STUDIO_ORIGIN` | Approved exact origin of customer-facing Studio; never redirect to caller-controlled URLs |

The file-backend Registry remains suitable only for local single-process research. Production or shared customer hosting requires independent review of network TLS termination, proxy trust, replay/ledger concurrency, storage mounts/backup, OIDC claims, connection lifecycle, incident response, and compliance.

## Operator smoke test

1. Confirm *default* behavior still refuses `GET /v1/drives/google/status` and `POST /v1/evidence/protected-admit` without OIDC and complete injected components.
2. Start the approved loopback Registry with the separately provisioned environment. Confirm the service binds only to loopback and `GET /health` and `GET /ready` provide readiness without leaking credentials.
3. Request a Drive endpoint with no bearer, a wrong service claim, a reader-only role attempting management, and a valid scoped identity. Record denials, not bearer tokens.
4. Complete OAuth only with the customer-approved account. Verify state replay rejection, selected-folder scope, explicit sync, metadata-only telemetry, source exclusion, independent offline signed review, and revoked delivery denial.
5. Execute the complete [A1–A7 customer acceptance protocol](customer-pilot-acceptance.md). Preserve redacted artifacts and SHA-256 checksums. The packet validator never self-approves a pilot.

## Rollback

Disable the pilot flag and stop the single process; revoke approved Google credentials, rotate affected keys and OIDC grants where required, delete the owner-scoped encrypted index using approved owner controls, and preserve only customer-approved redacted evidence according to retention policy. Explicitly document any separate copies/exports. Do not claim deletion of external copies or global application enforcement.

**Status: experimental staging composition only; customer pilot NOT ACCEPTED.**
