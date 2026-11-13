# US-068 — multi-replica Drive cursor coordination contract (implementation prerequisite)

Status: SPECIFIED / UNBUILT / UNTESTED / NOT ACCEPTED
Base: QualityRAG detached commit 12854aa. This document does not claim an implementation.

## Observed gap

`UserDriveIndex.inspectDriveChangeCursor` checks the current encrypted snapshot and active in-process syncs, then writes with `save`. This is process-local coordination; replicas with independent memory and filesystem views can both pass the check and overwrite one another's checkpoint. A read-then-write without a shared atomic conditional operation cannot prove checkpoint integrity.

## State and invariants

A cursor checkpoint is scoped by immutable `tenant/owner subject + connection identity + selected folder + baseline generation`. Store checkpoint encrypted; expose no Google page token or OAuth token in API responses, logs or traces.

- A cursor never advances past unprocessed changes.
- `CHANGED` irreversibly marks the existing baseline stale; no subsequent poll can reclassify that baseline as current.
- `UNKNOWN` never advances a checkpoint and never confers release approval.
- A complete, bounded scan with no relevant changes may advance only by a durable CAS against the exact baseline generation, prior cursor version and selected binding.
- A new sync baseline invalidates all outstanding poll leases and cursors for the previous generation.
- Concurrent workers must not let the later-finishing, older worker overwrite a newer checkpoint.
- A successful CAS is not enough to prove source-byte freshness, owner ACL authorization or release readiness; existing fresh byte/selection checks and signed review gates still apply.

## Smallest safe storage reuse

Prefer the existing shared, encrypted owner-index storage *only if* it supports an atomic conditional write that all running replicas share. Required interface:

```ts
loadCheckpoint(ownerKey): Promise<{
  baselineGeneration: string;
  cursorVersion: number;
  encryptedCursor: Uint8Array | null;
  bindingDigest: string;
  stale: boolean;
}>

compareAndSwapCheckpoint({
  ownerKey, expectedGeneration, expectedCursorVersion,
  expectedBindingDigest, nextEncryptedCursor, observedChange,
}): Promise<"ADVANCED" | "STALE" | "CONFLICT">
```

If current owner-index storage is a local file with no shared atomic CAS, **do not** silently use an in-memory lock or a local rename as a distributed solution. Either place cursor state in an already-operated transactional store shared by replicas, or keep polling explicitly single-writer and return UNKNOWN when exclusive ownership cannot be established. No new database is justified before this reuse check.

## Safe algorithm

1. Verify caller's owner identity, current Google connection binding, selected folder and baseline generation.
2. Load versioned cursor and reject missing/stale/ambiguous binding as UNKNOWN.
3. Page through Drive Changes with strict page/total-event/time budgets. Record no mutation while fetching. A selected-file, selected-folder, or relevant child event produces CHANGED. Missing parent metadata or provider errors produce UNKNOWN.
4. Re-read current binding; reject any generation, identity or folder drift.
5. Persist via the shared atomic CAS. Relevant change must commit STALE before returning a confirmed CHANGED to downstream consumers.
6. If CAS fails due to a competing poll or sync, return UNKNOWN (or safely restart within a separate bounded budget); never report MATCHED from stale observations.
7. Run live source-byte and complete inventory validation against the **same generation**. Produce MATCHED_AT_CHECK_TIME only if all evidence checks completed, the checkpoint CAS succeeded, and no binding drift occurred.

## Automatic polling

Use an authenticated, bounded worker with owner-scoped access only; never use a global service account to impersonate individual Drive owners. Schedule due checkpoints with deterministic jitter and quotas per tenant/owner and Google project. Persist next-attempt and last-complete metadata in shared storage to survive restart; retry transient errors with exponential backoff, never skip expired/ambiguous tokens. A push notification is only a trigger to poll, not trusted proof of content or permission change. Metrics include age of last completed check, UNKNOWN count, 410 cursor expirations, CAS conflicts, duration, page-budget aborts, change-to-STALE lag and quota responses without source IDs or tokens.

## Required adversarial tests (written specification; not executed)

| Scenario | Required result |
|---|---|
| Two replicas read same version, finish out of order | At most one checkpoint CAS succeeds; other UNKNOWN |
| Sync replaces baseline while poll is paginating | Old poll cannot write; UNKNOWN |
| Relevant changed file across middle page | Persistent STALE; no cursor advancement as clean |
| Removed file without parent evidence | UNKNOWN; no advancement |
| Google 410, timeout, 403, truncated pages, looped token | UNKNOWN; no advancement |
| Irrelevant changes, all pages complete, CAS wins | Advance opaque cursor only |
| Poll repeats same final page after crash | Idempotent or UNKNOWN; never falsely MATCHED |
| Disconnected owner, changed folder, changed delegated subject | Denied/UNKNOWN; no cross-owner reads |
| Quota budget exhausted | UNKNOWN and observable bounded retry |
| Permission denied | UNKNOWN, not proven revocation unless independently verified |

## Acceptance gate

Do not label US-068 READY/ACCEPTED until storage atomics are evidenced, concurrency tests executed against two separate process instances, real Google Drive integration and permission tests pass, and independent security/product acceptance is recorded. No build, deployment, merge, or release is authorized by this specification.

## Implementation increment — fenced resync (unbuilt)

The branch now contains `PgDriveCursorCoordinator.replaceBaseline`, which applies an
atomic PostgreSQL `UPDATE` conditional on the owner key, expected generation,
binding digest and cursor version. It accepts a distinct new generation after a
confirmed STALE baseline; a stale or competing writer receives `CONFLICT`.

`UserDriveIndex.sync` reads the expected checkpoint **before** Google network
calls, publishes its new database generation first, then writes the encrypted
local index only if CAS succeeds. If the process dies between these operations,
the baseline fingerprint differs and freshness checks return UNKNOWN. A
subsequent authorized resync can recover with a new generation. Absent a
usable start-page token, it refuses a coordinated resync without publishing
the local file.

**Unresolved architecture boundary:** A local index on separate replicas
remains inconsistent, so this is a fenced single-host pilot increment, **not**
a production multi-replica data plane. Migrating baseline content to a shared
encrypted transactional store, reconciling old index caches, and protecting all
read/review routes against stale shared state require further implementation.
The tests under `pg-drive-cursor-index-integration.test.js` use an in-memory
SQL behavior fake and are not proof of real PostgreSQL transaction isolation.
A real two-process PostgreSQL and Google Drive acceptance suite is required.

## 2026-11-11 shared encrypted baseline increment — prepared, unbuilt

Migration `013_drive_shared_encrypted_baseline.sql` adds an encrypted source
snapshot to the existing PostgreSQL checkpoint row without modifying the
checksum of migration 012. Both the current source baseline and the opaque
change cursor are encrypted using the existing owner-bound AES-GCM index
envelope and written in the **same conditional PostgreSQL statement** on
first sync and fenced replacement. No second database is introduced.

The protected live-source and selected-folder freshness paths now obtain
their baseline through `sharedBound`, which verifies owner, Drive binding,
integrity, and generation against the shared checkpoint. Local cache absence
or divergence cannot substitute evidence. STALE prevents protected reading.
Explicit owner resync preserves prior owner exclusions from the shared
baseline even when it was marked STALE. Shared index clear, folder change,
disconnect and relevant provider authorization failures trigger durable
checkpoint invalidation before local cleanup.

Unmigrated synchronous local routes (status/index/visibility/search and
governed candidate previews) are explicitly unavailable when shared mode is
enabled; local-only source-control writes are rejected to avoid silently
diverging owner privacy controls. This is a **conservative partial rollout**,
not an end-to-end feature completion. New regression cases are written but
unexecuted.

### Remaining prerequisites

1. Shared, per-user Google OAuth credential synchronization and rotation:
   current `GoogleDriveConnections.records` is process-local and file-backed.
2. Shared owner controls with CAS and their read/write UI adapters; restore
   coherent status, search, and candidate previews from the shared baseline.
3. Make all protected governance routes that access the index exclusively
   consume the same shared generation, including checks after asynchronous
   provider fetches and before ledger admission.
4. Real two-process PostgreSQL transaction tests with migration checks,
   crash and failover injection, as well as Google Drive pagination and
   permission-revocation evidence. Provider errors remain UNKNOWN.
5. Authenticated periodic polling, quotas, observability, production
   deployment controls, customer evidence and independent acceptance.

No build, test execution, merge or deployment was performed for this increment.

## 2026-11-11 owner source-control CAS increment (prepared; unbuilt)

A new `PgDriveCursorCoordinator.updateOwnerControls` uses a single PostgreSQL
conditional UPDATE on the expected owner, baseline generation, folder binding,
cursor version and non-STALE state. It commits an AES-GCM encrypted revised
source baseline, changes generation and marks STALE in the same update. The
authenticated `source-control` route now calls
`UserDriveIndex.controlSharedSource` when coordinated mode is enabled.

Both owner exclusions and re-inclusions invalidate governed use: a control
mutation never silently grants SAT or release permission. A successful edit
requires a new authorized Google resync before protected use. The existing
shared-baseline resync preserves excluded file IDs and reasons through the
stored control history; failed, concurrent and cross-owner edits never write
a local-only substitute. The synchronous legacy `controlSource` method
continues to reject coordinated mode.

Additional in-memory SQL harness tests cover CAS fencing, cross-owner denial,
control changes surviving resync, and stale-state persistence. These tests
have **not** run and are not equivalent to two-process PostgreSQL acceptance.

Remaining: coherent shared status/search/candidate adapters; durable per-user
Google OAuth connections and refresh locking; authenticated scheduled polling
and quota budgets; independent ACL/revocation proof; real database/provider,
authorization, accessibility and customer acceptance tests. No builds, merges,
CI runs or deployments were initiated.

## 2026-11-11 shared OAuth groundwork (prepared, unbuilt)

Implemented additive migrations 014 (encrypted per-user Google credentials) and
015 (encrypted OAuth pending states) on the existing Registry PostgreSQL.
`PgDriveOwnerCredentials` derives HMAC owner keys, encrypts stored Google
credentials with AES-256-GCM and an owner-bound AAD, supports explicit
authorization, transactional `SELECT ... FOR UPDATE` refresh with a bounded
lock/statement timeout, and disconnect tombstones that erase credential
ciphertext. Re-consent is the only operation that may revive a disconnected
owner record. Source-index cryptographic keys remain separate.

`PgDriveOAuthPending` stores encrypted owner+PKCE verifier for 10 minutes
and consumes states by `DELETE ... RETURNING`; callbacks routed to another
Registry replica can therefore verify the same one-time state. The existing
`GoogleDriveConnections.startCoordinated` and OAuth callback opt into this
shared state when the PostgreSQL cursor feature is enabled. The old
single-process pilot's sync start method is retained.

**Critical pending wiring:** `PgDriveOwnerCredentials` is a standalone
repository implementation, **not yet the active credential store used by
`GoogleDriveConnections`**. The connector's `status`, `decrypt`,
`replace`, `refresh`, `selectFolder` and `disconnect` continue to rely
on the process-local credential JSON file. A successful cross-replica OAuth
callback can still write credentials only to the callback replica until
these methods and their route consumers are migrated. The shared PKCE
change must not be represented as complete multi-replica Google Drive
connectivity. No database migrations or tests have been executed.

The next changes must wire a coherent asynchronous credential API across
the scope/authorization routes, eliminate local token lookups in coordinated
mode, and verify refresh, logout and re-consent concurrency against two
actual PostgreSQL clients. State and refresh secrets must never appear in
logs, telemetry or API responses.

## 2026-11-13 integration increment — built, executed and wired

This increment builds and **executes** the earlier groundwork and closes the cross-replica gaps
listed above. Status remains **not READY/ACCEPTED** (see the acceptance gate).

**Executed for the first time.** The full Registry suite runs against a real PostgreSQL 16:
210 tests pass (main had 131). The first run of the branch found five regressions in the existing
routes, now fixed:

- `scoped-drive-control` called `startCoordinated`/`clearCoordinated` unconditionally. Narrower
  implementations now fall back to `start`/`clear`.
- The new dependency-status test built a handler that violated the `createHandler` invariant.

**Real two-process PostgreSQL acceptance** (`pg-drive-two-process.test.js`). Each race runs as two
separate OS processes with their own pools, released together by a barrier, and is stable over
repeated runs:

| Scenario | Result |
|---|---|
| Two replicas advance the same cursor version (5 rounds) | Exactly one `ADVANCED`, one `CONFLICT` per round |
| Fenced resync racing an old-generation poll | Never both; an old-generation poll can never write afterwards |
| `markStale` racing `advance` | STALE wins and is irreversible; later advances `CONFLICT` |
| One OAuth state consumed on two replicas | Exactly one succeeds; the other gets `DRIVE_OAUTH_STATE_INVALID` |
| Two replicas refresh the same credential | Serialised: each sees a different predecessor; revision +2 |
| Refresh held past `lock_timeout` | The waiter fails closed (`lock timeout`) and never sees a credential |
| Refresh after disconnect | `DRIVE_CONNECTION_NOT_FOUND`; the tombstone is not resurrected |

**Shared credentials wired (was "critical pending wiring").** With `QUALITYRAG_DRIVE_CURSOR_PG=true`:

- **Store:** the server injects `PgDriveOwnerCredentials`, and `GoogleDriveConnections` reads and
  writes owner credentials only through it. The local credential file is never read or written in
  this mode.
- **Connector methods:** `status` is async in this mode. Exchange, folder selection
  (`selectFolder`, row-locked, refuses tombstones), token refresh (row-locked; a waiting replica
  reuses the rotated token) and disconnect (shared tombstone first) all go through the store.
- **Call sites:** every route awaits `status`.
- **All-or-nothing:** shared cursors, shared OAuth state and shared credentials are enabled
  together (`PILOT_SHARED_DRIVE_STATE_INCOMPLETE`).
- **Evidence:** `drive-shared-credentials.test.js` uses two connector replicas with separate local
  files and separate pools on real PostgreSQL. It covers:
  - connect started on A and completed on B;
  - a folder chosen on B is A's folder;
  - concurrent expired-token refresh rotates once at Google;
  - disconnect on A stops B immediately, and re-consent reconnects without the old folder.

**Shared read adapters (was "explicitly unavailable").** Status, index, visibility, search and
governed candidate checks now read the verified shared baseline (`sharedView` on top of
`sharedBound`) instead of answering 503:

- A STALE checkpoint is reported as STALE, search returns no hits (`SYNC_REQUIRED`), and the
  candidate check is `NOT_CURRENT`.
- Owner exclusions are still enforced on a STALE baseline, so a denial is never hidden behind
  staleness.
- **Evidence:** `drive-shared-index-real-pg.test.js` uses two index replicas on real PostgreSQL. It
  covers reading from a replica without a local index, a different account binding being refused,
  an exclusion made on A being enforced on B, and drift inspection (clean advance, durable STALE,
  then UNKNOWN).

**Still not evidenced (blocking acceptance):**
- Live Google Drive OAuth, pagination, 410 cursor expiry and permission-revocation behaviour; Google
  is a local fake in every test above.
- Authenticated scheduled polling with quotas and observability.
- Production deployment controls: the pilot remains loopback-only.
- Accessibility and customer acceptance, and independent security/product acceptance.
- `QUALITYRAG_DRIVE_ENCRYPTION_KEY` currently encrypts both shared OAuth state and shared
  credentials (separated by AAD). Dedicated keys per purpose would be stricter.
