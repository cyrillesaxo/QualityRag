# QualityRAG Studio — Personal cloud-drive connections

**Status:** Google Drive **connection, folder configuration, and opt-in isolated text indexing** implemented on the draft Studio branch. Requires administrator-managed Google OAuth credentials and signed per-user OIDC identities. No production Google credentials were supplied or connected by this PR. Microsoft OneDrive and Dropbox remain future provider adapters. **Connection alone never downloads or indexes content; sync requires an explicit user action.**

## What the user can configure in Studio

The **My cloud drives** panel appears immediately under the registry connection panel, before Evidence Assurance telemetry.

- Connect **their own** Google account using a Google authorization dialog.
- See the account email returned by Google (not inferred from the registry login).
- Browse Google Drive folders, including root and nested folders.
- Explicitly choose one folder as the source for this workspace.
- Preview up to 100 **file metadata** entries directly under that folder (name, ID, MIME type, size, modified timestamp).
- Reconnect, refresh or disconnect without viewing/storing provider tokens in the browser.
- Detect a disabled/misconfigured registry with a clear operator-facing message.

This is read-only connectivity and folder configuration plus a **separate encrypted, per-user text index**. Unlike the existing Semantic Store, this pilot index does not provide semantic embeddings or the full Codex grammar. **Never put one user's Google documents into the shared local Semantic Store workbench.**

### Critical Google permission scope

This prototype requests Google's `https://www.googleapis.com/auth/drive.readonly` scope: **account-wide read-only Drive access**, not OAuth access only to the selected folder. Folder selection is an **application-level operational constraint**, not a Google-scoped permission. The server's OAuth credential technically has broader read access than the folder picker. This distinction is shown in the Studio UI.

For an enterprise offering, consider Google Picker + `drive.file` file-specific authorization, Google OAuth restricted-scope verification, and an isolated ingestion/sync design before enabling customer content access. Google OAuth verification and potentially a security assessment may be required for restricted scopes. Confirm Google's current policies during release preparation.

## One-time server setup

Requirements: Google Cloud project, OAuth consent configuration, Google Drive API enabled, **Web application** OAuth client, an exact approved redirect URL, and a user authentication system issuing verified OIDC identity JWTs. No Google client secret belongs in the browser, repo, PR, or a chat message.

The prototype's registry operates in **single-process file backend + OIDC mode only**, intentionally not the shared local token or multi-instance Postgres mode. Keep it bound to loopback during development; use TLS, reviewed tenancy, key rotation, and a shared safe state store before public deployment.

Example for a **local trusted developer computer** (place actual values in a private environment manager):

```sh
export QUALITYRAG_AUTH_MODE=oidc
export QUALITYRAG_REGISTRY_BACKEND=file
export QUALITYRAG_OIDC_ISSUER="https://YOUR-TRUSTED-ISSUER/"
export QUALITYRAG_OIDC_AUDIENCE="qualityrag-registry"
export QUALITYRAG_OIDC_JWKS_URI="https://YOUR-TRUSTED-ISSUER/.well-known/jwks.json"

export QUALITYRAG_DRIVE_FILE="$PWD/.qualityrag/private-user-drives.json"
export QUALITYRAG_DRIVE_INDEX_DIR="$PWD/.qualityrag/private-drive-indices"
export QUALITYRAG_DRIVE_ENCRYPTION_KEY="$(openssl rand -base64 32)"
export QUALITYRAG_GOOGLE_OAUTH_CLIENT_ID="YOUR_WEB_OAUTH_CLIENT_ID"
export QUALITYRAG_GOOGLE_OAUTH_CLIENT_SECRET="YOUR_WEB_OAUTH_CLIENT_SECRET"
export QUALITYRAG_GOOGLE_REDIRECT_URI="http://127.0.0.1:5055/v1/drives/google/callback"
export QUALITYRAG_STUDIO_ORIGIN="http://127.0.0.1:5173"

npm --prefix apps/registry install
npm --prefix apps/registry start
```

**Do not generate a new encryption key on every restart.** Store it safely and persistently in a secrets manager. If the key changes or is lost, saved account credentials cannot be decrypted. A brand-new `openssl rand` value is only appropriate when creating the environment **once**, then storing it securely. Never commit the encrypted credentials file, key, token, or client secret.

Use the **same hostname** for Studio and Google redirect in local development (here `127.0.0.1`). The exact URI must be registered in Google Cloud's authorized redirects. The Studio origin must be exact; the connector rejects non-HTTPS callback origins except loopback.

### Required OIDC roles

The signed registry JWT must include a stable `sub`, approved issuer/audience and appropriate role claims. Both roles are needed for the full UI:

```json
{
  "roles": ["drive.reader", "drive.manager"]
}
```

- `drive.reader`: connection status, browse folder metadata, inspect selected-folder file metadata.
- `drive.manager`: create the OAuth authorization request, select the folder, disconnect.
- `policy.reader` etc. are separate governance roles; no Drive role automatically grants PackSpec access.
- The owner is the **OIDC issuer + subject**, not a supplied email or browser-provided user ID. OIDC scopes are checked on the server. Local registry shared bearer mode **cannot** enable Drive connectivity.

The registry currently takes an authenticated bearer token pasted into Studio; it does **not** provide a complete interactive sign-in/PKCE flow for the registry itself. For production UX, first implement proper OIDC login and refresh within a hardened backend-for-frontend architecture.

### Configuration endpoints

| Method | Endpoint | Effect |
|---|---|---|
| `GET` | `/v1/drives/google/status` | Only the current subject's saved connection status and folder selection |
| `POST` | `/v1/drives/google/start` | Creates a short-lived OAuth authorization URL with server-held state + PKCE verifier |
| `GET` | `/v1/drives/google/callback` | One-time Google OAuth callback; binds the token to the subject from the start request; redirects to the fixed Studio origin |
| `GET` | `/v1/drives/google/folders?parentId=root` | Lists accessible folders for this user's account |
| `POST` | `/v1/drives/google/folder` | Selects a validated folder using `{"folderId":"ID"}` |
| `GET` | `/v1/drives/google/files` | Returns at most 100 file-metadata entries directly inside the selected folder |
| `POST` | `/v1/drives/google/disconnect` | Deletes local encrypted credentials **and the subject's index**; attempts remote Google token revocation |
| `GET` | `/v1/drives/google/index` | Index status, coverage, counts and freshness; read role |
| `POST` | `/v1/drives/google/sync` | With empty JSON object, explicitly build/replace only the current subject's selected-folder text index; manage role |
| `POST` | `/v1/drives/google/search` | Lexical candidate search with `{"query":"hidden exception"}`; read role |
| `POST` | `/v1/drives/google/clear-index` | Immediately delete that user's local index without changing Drive files; manage role |

The OAuth callback is the only route not requiring a bearer token. It consumes a cryptographically random 10-minute, single-use server-side state and uses a PKCE code verifier. No access/refresh tokens are returned to Studio. On callback failure, no credential is stored and the user sees a generic failure URL.

### Storage boundary

Every user's provider token and folder selection is encrypted in a separate AES-256-GCM payload, with associated data binding the token to the verified OIDC subject. The on-disk lookup key is the SHA-256 digest of that subject. Storage is a local file with restrictive permissions, and the encryption key is configured **out of band**. All Google API requests run from the registry; the browser cannot send arbitrary Google API URLs.

This is appropriate for a **local single-instance research prototype**, not for public multi-tenant durability or regulatory assurance. It still needs a proper secret manager, database isolation, backoff/rate limits, stronger OAuth/CSRF hardening, signed user-session UX, backup/recovery, token lifecycle and retention reviews before production.

## Explicit per-user text indexing — pilot only

Setting `QUALITYRAG_DRIVE_INDEX_DIR` opt-in enables the new **My private Drive text index** subpanel. It requires the same verified OIDC user identity as the connection, and a selected **non-root** folder.

1. Connect your own Google account and explicitly select a specific folder (not the whole Drive root).
2. Choose **Sync selected folder now**. This retrieves only direct-child text files in that folder; no recursive subtree traversal.
3. Studio reports files listed, indexed, unsupported, failed, oversized, truncated, and last synced. Coverage is `PARTIAL` whenever files cannot be included. This is not a guarantee of full Drive discovery.
4. Search with text such as `hidden exception`. The index produces lexical matches with a stable pseudonymous source ID, source revision, file name, and exact text-line anchor.
5. Open **Evidence visibility and owner control** to inspect the exact per-source inventory, source-revision digests, omitted/failed file reasons, and local activity history. An authorized owner can exclude individual sources from private lexical search with a reason, or explicitly include them again. Exclusion persists across resync and source revisions; **exclusion does not erase encrypted text**, and inclusion never constitutes PackSpec approval.
6. Export the unsigned visibility report to inspect coverage independently. It is not a signed audit attestation.
7. Use **Delete my local index** to erase cached text. Selecting a different folder, replacing the Google connection, or disconnecting purges the prior per-subject index. A successful resync atomically replaces the old snapshot and removes deleted/moved files. In-flight synchronizations are fenced: they cannot recreate an index after a disconnect, folder switch, or explicit deletion.

Supported pilot MIME types: `text/plain`, `text/markdown`, `text/csv`, `application/json`, `application/vnd.google-apps.document` (exported by Drive as `text/plain`). PDF, DOCX, Sheets, Slides, media, OCR, image embeddings and video scene indexing are **not** included in this per-user Drive importer.

**Bounds:** at most 40 supported text files per folder and at most the first 100 direct-child metadata entries; if Google indicates more files, the sync fails rather than claiming complete coverage. Maximum content per text file is 96 KB, with a total retained text limit of 1.5 MB. The index becomes **STALE** after 60 minutes, and search will return no matches until an explicit resync. Unsupported, failed, oversized, or line-truncated sources are counted separately. Exact source content and filenames are stored encrypted with AES-256-GCM in a user-keyed, subject-authenticated local file, with restrictive OS permissions.

**Security boundary:** Every content fetch independently requests Google file metadata and confirms the actual parent folder is the user's selected folder. The code never accepts a browser-submitted arbitrary file ID or download URL for indexing. Requests go only to hard-coded Google Drive API endpoints, and downloads have strict byte limits. The result is isolated from other users through OIDC subject scoping and per-subject encrypted snapshots.

### Policy-bound source check in Studio

The **Evidence visibility and owner control** panel also offers **Check candidate** for each indexed source. To use it, the signed user must possess `drive.reader` and `evidence.reader` and have `qualityrag_services` scope for the selected service/environment. Studio loads only the approved requirement IDs from `GET /v1/drives/google/governed-requirements` and submits the selected source ID, revision, line anchor and requirement to `POST /v1/drives/google/governed-check`. The registry resolves the approved PackSpec; the browser cannot send arbitrary policy definitions.

An explicitly excluded source receives `REFUSE` regardless of stale metadata or a changed submitted revision. Missing, moved, stale, changed or otherwise unreviewed sources remain `INCONCLUSIVE`, with clear reasons. A source included in private search also remains `INCONCLUSIVE` until semantic support and provenance are actually verified. The response labels `evaluationAdmitted=false`, `meaningVerified=false` and `independentProvenanceVerified=false`.

This is **candidate eligibility checking**, not a full, signed QualityRAG business-answer verdict. Other integrations must separately enforce the same owner controls; generic `POST /v1/evidence/evaluations` is a separate telemetry path and cannot be assumed to enforce Drive exclusions. The check is transient: it is not a signed audit record or automatically recorded in the telemetry ledger. Run `npm --prefix apps/registry run drive:governed-demo` to reproduce the owner-exclusion and re-inclusion sequence using synthetic data.

### Reviewer-initiated telemetry

Studio separates **Check candidate** (non-mutating preview requiring
`drive.reader` and `evidence.reader`) from **Record challenge (reviewer)**
(additionally requiring `evidence.reviewer`, with 20 writes/minute
per reviewer). Both resolve the PackSpec server-side and can only
`REFUSE` or remain `INCONCLUSIVE`. The recorded action produces a
local unsigned ledger receipt and increments the Evidence Assurance
candidate-check count, but does not record raw source text or change
evidence admission. Missing reviewer privileges produce an explicit
403 instead of silently granting recording access.

### Customer-signed approval path

For protected services with a configured public-key trust list, Studio's
**Customer-signed protected evidence review** panel lets an owner submit an
offline package signed separately by the custodian and semantic reviewer.
Only the registry verifies signatures, the current Drive file bytes,
source exclusions, and the approved PackSpec; it then records a decision
and returns an owner-only portable receipt. This is distinct from the
`governed-check` preview, which always remains non-admitting.

[Offline signing and Python replay guide](PROTECTED-HUMAN-REVIEW-ADMISSION.md).
The pilot never requests private signing keys in the browser and supports
only human-approved, single-origin/no-freshness requirements. No Google
production customer pilot is claimed.

**Evidence boundary:** This is a bounded *lexical* index, not the Semantic Garden grammar, full QualityRAG governed retrieval, an LLM answer, semantic vector search, or a validated evidence receipt. Source-origin independence and authenticity are not inferred from file count or matched lines. No candidate becomes an `ADMIT` result until an authorized PackSpec evaluation and customer source review happen separately.

**Lifecycle limitations:** Remote Google file revocation and deletions are checked on the next explicit sync; an already encrypted local snapshot could remain searchable for up to its 60-minute freshness window after remote permission changes. This is not acceptable for high-sensitivity regulated tenants without an authorization recheck, event-driven deletion, and retention controls. The index is single-process, single-instance and local-file-based, not a hardened production multitenant storage service. Explicit deletion is local; it does not modify or delete the original Google files.

See [Credibility = Visibility + Control](CREDIBILITY-VISIBILITY-CONTROL.md) for the customer acceptance test and exact boundaries between source selection, source custody and evidence admission.

## Tests and verification

```sh
npm --prefix apps/registry test
npm --prefix apps/studio run build
```

The registry tests use a fake Google provider (no real tokens) to assert:

- Alice and Bob connect separate Google accounts to separately verified OIDC subjects.
- One user cannot read or alter another's Google connection.
- OAuth state is single-use; an expired/falsified state fails closed.
- File contents, raw Google access tokens and refresh tokens are not returned to the browser.
- Saved tokens, user emails, folders and account state are encrypted on disk.
- Selecting a folder is explicit and checked against Google's folder metadata.
- Disconnect removes the local token without changing the other user's account.
- Studio visibly distinguishes connection/metadata preview from actual indexing.

The tests also exercise per-user isolated encrypted indexing, text-export source anchors, selected-folder parent checks, stale searches, file replacement on resync, and local index deletion. No live Google OAuth end-to-end test has been completed without project-specific client credentials and a verified consent screen.

## Next production milestones

1. Implement actual OIDC sign-in/refresh for Studio instead of manually supplied bearer tokens.
2. Replace account-wide `drive.readonly` with Google Picker + `drive.file` if buyer permission requirements demand file-specific grants.
3. Add genuinely user-isolated source importer and background sync with revocation/deletion semantics; the existing local Semantic Store worker **must not** be reused as a multi-user destination without isolation.
4. Offer Microsoft OneDrive and Dropbox through matching per-user OAuth adapters after comparable security reviews.
5. Connect authorized imported source lineage and tenant-bound indices to Evidence Assurance; never infer provenance independence from multiple uploaded files.
