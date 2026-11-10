# Protected dependency-status — read-only policy/Drive drift detection

**Status:** prepared implementation on an unbuilt detached commit; not deployed, tested or accepted.

The owner-authenticated endpoint `GET /v1/evidence/protected-decisions/{uuid}/dependency-status` reuses existing QualityRAG protected decision history, active policy resolution and per-subject Google Drive connection metadata.

It requires `evidence.reader`, `drive.reader` and the matching `qualityrag_services=serviceId@environment` scope. The Registry verifies the exact decision owner before revealing metadata. It observes:

- `revoked`: the protected decision has an appended revocation event
- `policyState`: active PackSpec SHA-256 `UNCHANGED`, `CHANGED` or `UNKNOWN` compared with the admitted decision
- `driveState`: the owner's Drive is `BOUND`, `FOLDER_CHANGED`, `DISCONNECTED`, or `UNKNOWN` relative to the historically signed folder

When revocation, policy drift or Drive disconnection/folder change is positively observed, `dependencyState=STALE`. Otherwise `dependencyState=UNKNOWN`, **never SAT or current approval**.

No source text, Drive folder identifier, access token, unreviewed content or signing key is sent. This endpoint **does not** perform Google Drive live-byte revalidation, verify present-day owner ACLs, check reviewer key revocation history, or create a new protected use. All responses declare `sourceBytesRevalidated:false`, `reviewerKeyValidityRevalidated:false`, `permissionRevalidatedForUse:false`, `releasePermitted:false`.

A network outage or missing policy should produce UNKNOWN and never allow previously stale reports to become current. Balafons may conservatively and irreversibly invalidate a linked local lineage when Registry reports a known stale condition. Binding a Balafons lineage to the decision is an owner-declared reference, **not proof that the chosen Balafons sources were reviewed in QualityRAG**.

**Before acceptance:** independent OIDC integration, real Drive and policy mutation tests, proven reviewer-key revocation lifecycle, authenticated provider webhooks/change tokens, multi-replica recovery and production audit. The endpoint should be subject to standard authenticated read rate limits and monitoring.

## Live Google source revalidation extension (prepared, NOT executed)

The dependency endpoint now optionally invokes the same signed human-witness
verification and `driveIndex.verifyLiveApprovedWitnesses` pipeline used by
QualityRAG's grounded-delivery path. It checks the owner-bound custodian and
semantic-reviewer signatures against the active policy, re-downloads exact
Google Drive source bytes from the selected folder under the connected owner's
credential, checks original anchored lines and owner source-exclusion controls,
and requests full bounded constraint/relationship scans.

The response adds:

- `liveSourceState=MATCHED_AT_CHECK_TIME`: the bounded signed witness
  scope passed current provider-byte/anchor review and contradiction scans at
  `liveCheckedAt`. `sourceBytesRevalidated=true`.
- `liveSourceState=CHANGED`: a positively observed byte/line revision,
  missing selected source, owner exclusion or newly detected source conflict.
  `dependencyState=STALE` and `sourceBytesRevalidated=false`.
- `liveSourceState=UNKNOWN`: provider outage, stale index, unavailable
  verifier or other unestablished result. Never infer source verification.

The response **always** preserves `releasePermitted=false`,
`reviewerKeyValidityRevalidated=false` and
`permissionRevalidatedForUse=false`. It returns no source text or answer,
does not create a protected-use ledger event and is not globally complete
semantic verification.

**Operational constraints:** this is an expensive read requiring real Google
API calls; rate limiting, provider quotas, audit sampling, output caching
discipline, full provider-permission change signals, and multi-process
transaction isolation remain unresolved. A MATCHED result is point-in-time
only. No build, tests or deployment have been executed.


## Owner-selected folder change polling (implementation draft; no build)

The existing encrypted `UserDriveIndex` snapshot is reused as the durable
owner-scoped checkpoint. `inspectSelectedFolderDrift(subject, connector)`
reads a fresh full folder inventory under that owner's Google Drive access
token and compares exact file IDs/MIME types against the indexed selection.
It then re-downloads every indexed text file within existing per-file and
folder limits and compares its SHA-256 with the encrypted baseline.
The check returns **CHANGED** for added/removed files, a newly unsupported
type, owner exclusions, or mismatched bytes; **UNKNOWN** for partial/truncated
listings, stale or incomplete index, missing/denied access, concurrent
resync, or provider failure; and **MATCHED_AT_CHECK_TIME** only after a
bounded, complete comparison. No file names, IDs, source content or raw
permissions are returned. No automatic index overwrite is performed.

The protected-decision dependency endpoint combines this folder check with
signed-witness live revalidation, source exception scanning, current PackSpec
and decision revocations. It does not generate a grounded answer or consume
a protected-use event. A CHANGED result propagates a conservative STALE
decision to a linked Balafons lineage on its next authorized read.

**Limitations:** this is a read-triggered bounded poll, not a background
scheduler, watch-channel subscription or complete Drive permission audit.
A positive match is point-in-time and cannot prove that Google files or
ACLs remained unchanged after the comparison. A provider 403 stays UNKNOWN
until trusted ACL data establishes revocation. Multi-replica locking,
poll budgets, trusted reviewer-key revocation, and real provider pilot
validation remain open. Code and tests are staged **without build or CI**.


## Durable owner-scoped Google Changes cursor (implementation draft)

The OAuth connector now supports Drive v3 `changes/startPageToken` and
bounded paginated `changes` requests, using the same encrypted per-user
authorization as existing Google Drive reads. A fresh opaque start cursor is
captured **before** an authorized Drive index rebuild, then stored inside
that owner's existing AES-GCM index snapshot. No cursor is sent to the UI.

At an authorized protected-decision dependency read, QualityRAG compares
the current folder inventory and bytes to the encrypted snapshot and then
checks the Google Changes cursor. Changes for an indexed file, the selected
folder itself, or a newly observed child mark the source **CHANGED**. Removed
events with unknown parentage, incomplete pages, expired/invalid cursors,
Google 403/429/5xx, missing cursor, and pagination beyond the fixed budget
yield **UNKNOWN**, not SAT or permission revocation. Unrelated events
are permitted only after all bounded pages complete; the new cursor is
atomically saved in the encrypted owner index. Previously indexed source
bytes and control flags are never overwritten by polling.

This implementation is **read-triggered** rather than a cron or push
subscription: there is no scheduled cross-tenant scan, Google webhook,
background worker or guaranteed maximum detection latency. A lost index
requires a fresh owner-authorized sync to establish a new cursor. Multi-
replica coordination/compare-and-swap, production OAuth scope verification,
provider quotas, Google change-token expiration recovery, and customer
permission-revocation pilots remain acceptance blockers.

A Google permission failure alone cannot distinguish revoked access from
an outage or expired token. It must remain UNKNOWN; claiming an independently
verified ACL revocation requires separate authoritative evidence. No
compile, test execution, CI, merge or deployment has occurred.
