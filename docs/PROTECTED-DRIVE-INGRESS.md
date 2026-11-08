# Protected Drive evidence ingress — visible, fail-closed pilot

**Status:** Experimental, single-instance registry. **Not deployed or customer-certified.**
This is a deliberately conservative bridge while full authenticated source custody,
semantic evidence review, and enforcement in external RAG SDKs are under construction.

## Why it exists

A user can exclude a document in Studio's private Google Drive index. Without a
registry protection boundary, an application with `evidence.ingest` permission can
still submit invented `src_...` and `org_...` strings to the generic
`POST /v1/evidence/evaluations` endpoint and obtain a misleading `ADMIT`.

**A visible UI toggle is not effective governance if the runtime ignores it.**

### Protected mode (new)

For each explicitly configured `serviceId@environment`, the registry blocks
**all generic, unreviewed evidence submissions**. It returns HTTP 403
`PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED` before they reach the metadata
evaluator. This rejects both arbitrary source tokens and apparently good ones.
There is **no bypass flag**, automatic exception, or silent fallback.

The customer's scoped Evidence Assurance UI displays:
- **PROTECTED** or **LEGACY** per service/environment;
- the bound approved PackSpec ID/version/digest;
- whether generic evidence ingestion is blocked;
- the number and most recent time of attempted submissions blocked;
- explicit remaining trust boundaries.

Blocked attempts are appended to the existing hash-chained local evidence ledger,
containing **only** a timestamp, service/environment, hashed actor, policy digest
and fixed reason. **No prompt, customer document, raw request ID, source token,
retrieved passage, or PAN** is copied into the denial record. The log is locally
tamper-evident but **not externally attested**. Observed counts do not measure
all eligible application requests.

## Configuration

This capability is opt-in and requires the same OIDC signed identities and
local, single-process Drive integration as the Studio pilot. The evidence
ledger and per-user Drive index **must** also be configured. Never commit
credentials, a database password, or encryption keys.

```sh
export QUALITYRAG_AUTH_MODE=oidc
export QUALITYRAG_REGISTRY_BACKEND=file
# Configure Google OAuth, OIDC issuer/audience/JWKS, Drive private index
# and encryption key using docs/STUDIO-PER-USER-DRIVE.md.
export QUALITYRAG_EVIDENCE_LEDGER_FILE="$PWD/.qualityrag/evidence.jsonl"
export QUALITYRAG_PROTECTED_DRIVE_SERVICES="claims-api@dev,legal-assistant@test"

npm --prefix apps/registry install
npm --prefix apps/registry start
```

Only explicitly enumerated service/environment pairs are protected. Duplicate
scopes, malformed identifiers and incomplete security prerequisites block
startup. Protection does **not** start automatically for every newly registered
service: validate the exact service/environment inventory before the pilot.

The ledger retains a local activation record for each protected scope. If a
future restart omits a previously protected scope while using the same ledger,
startup refuses with `PROTECTED_DRIVE_CONFIGURATION_DOWNGRADE`, rather
than silently returning to accepting unreviewed evidence. There is currently
**no automatic unprotect endpoint** or downgrade approval workflow. A privileged
actor with filesystem access could still rewrite or replace an unanchored ledger;
operational custody and external anchoring remain production work.

## API

An identity with `evidence.reader` **and** the signed
`qualityrag_services` scope for the service can inspect protection:

```sh
curl -fsS -H 'Authorization: Bearer READER_IDENTITY_TOKEN' \
  'http://127.0.0.1:5055/v1/evidence/enforcement?serviceId=claims-api&environment=dev'
```

Example semantic fields:

```json
{
  "schema": "qualityrag.drive-protection/v1",
  "protected": true,
  "mode": "BLOCK_UNATTESTED_GENERIC_EVIDENCE",
  "genericEvidenceIngress": "BLOCKED",
  "sourceAdmission": "NOT_IMPLEMENTED",
  "independentSourceVerification": "NOT_IMPLEMENTED",
  "globalApplicationEnforcement": false,
  "guardTelemetry": {
    "observedBlockedAttempts": 2,
    "coverage": "REGISTRY_INGRESS_ONLY",
    "externallyAnchored": false
  }
}
```

These are **example fields**, not a real customer result. An unprotected service
is explicitly marked `LEGACY_METADATA_GATE`. Legacy `ADMIT` events recorded
**before** protection was enabled can remain visible in history; do not present
them as protected approvals.

## Real HTTP demonstration with synthetic data

```sh
npm --prefix apps/registry install
npm --prefix apps/registry run protection:demo
```

The demonstration uses mocked IdP subjects and synthetic source tokens. It
shows `claims-api@protected` rejecting a generic event with HTTP 403 and
counting the denied ingress, while `claims-api@test` still uses the legacy
metadata evaluator and can return `ADMIT`. The contrast makes both the
effective control and the legacy exposure observable.

## Non-negotiable limits

1. This protects **one registry's generic evaluation-ingestion endpoint** for
   explicitly configured service/environment pairs. It does **not** constrain
   independent inference services, model-generated text, direct database reads,
   or alternate registry installations.
2. This mode intentionally **blocks even legitimate evidence** at generic
   ingress. The separate `/v1/drives/google/governed-check` endpoint remains
   a candidate-only review and never admits unverified meaning/provenance.
   Therefore it is **not** a complete production answer-generation path.
3. Source authorship, independence, semantics, policy completeness and
   customer custody remain unverified. A local file ledger does not satisfy
   regulated audit requirements.
4. The next step is a separately scoped **reviewed source-attestation gate**
   that proves source authorization, pinned revision, independently approved
   PackSpec and source custody before an evidence event can be admitted.
   That gate requires an adversarial independent test before protected services
   can safely execute business decisions.
5. Deployments require real OIDC sign-in, restricted Google OAuth scope review,
   tenant-isolated storage, stronger revocation/retention enforcement, proper
   key lifecycle, alerting for denied ingress and external log anchoring.

**Product rule:** The UI must never show a simple "green/secure" indicator
without displaying exactly **what is enforced, what is merely recorded, and
what can still bypass this instance**.
