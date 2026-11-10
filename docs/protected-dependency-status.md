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
