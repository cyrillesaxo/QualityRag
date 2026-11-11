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
