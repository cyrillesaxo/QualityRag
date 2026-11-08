# QualityRAG Studio cloud-drive integration contract

The Studio now exposes a fail-closed cloud-drive panel for Google Drive, OneDrive/SharePoint, Dropbox and Box. **This PR is UI integration only. It does not establish OAuth consent, access to user drives, or ingestion.** Controls remain disabled until a compatible authenticated registry connector API is deployed.

## API contract (not yet implemented)

- `GET /v1/connectors` → `{connections:[{id,provider,display_name,status,scopes,last_sync_at,indexed_count}]}`.
- `POST /v1/connectors/{provider}/authorize` → `{authorization_url,state_issued:true}`. The server MUST issue a one-time CSRF state, PKCE challenge, and registered HTTPS callback, then store credentials server-side.
- `POST /v1/connectors/{id}/sync` → queue an ACL-aware incremental sync; do not return a false success before queued.
- `DELETE /v1/connectors/{id}` → revoke provider credentials and disable future sync; handle indexed-data retention under tenant policy.

## Required server controls

1. Google OAuth with Drive read-only scopes, user consent, encrypted refresh tokens, tenant and principal binding. A Drive homepage URL is not an OAuth endpoint or access grant.
2. Provider adapters for Microsoft Graph, Dropbox and Box, each using minimal read scopes.
3. Permission-filtered indexing with source IDs, version IDs, MIME type, document revision, owner, ACL snapshot, sync watermark, deletion/tombstone state and traceable extraction anchors.
4. Respect Google Workspace export formats, quotas, API backoff, token revocation, rate limits and source file changes.
5. Fail closed on expired tokens, missing permissions, deleted sources, missing source spans or incomplete indexing. No cross-tenant retrieval.
6. Add server integration tests and audit telemetry before enabling the UI.

Recommended first implementation: Google Drive OAuth + metadata-only inventory; then bounded read-only indexing; then ACL-filtered Semantic Store retrieval; finally other providers. Never paste Google tokens into Studio.
