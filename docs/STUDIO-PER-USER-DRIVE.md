# QualityRAG Studio — Personal cloud-drive connections

**Status:** Google Drive **connection + folder configuration** implemented on the draft Studio branch. Requires administrator-managed Google OAuth credentials and signed per-user OIDC identities. No production Google credentials were supplied or connected by this PR. Microsoft OneDrive and Dropbox remain future provider adapters. **No automatic download or ingestion occurs.**

## What the user can configure in Studio

The **My cloud drives** panel appears immediately under the registry connection panel, before Evidence Assurance telemetry.

- Connect **their own** Google account using a Google authorization dialog.
- See the account email returned by Google (not inferred from the registry login).
- Browse Google Drive folders, including root and nested folders.
- Explicitly choose one folder as the source for this workspace.
- Preview up to 100 **file metadata** entries directly under that folder (name, ID, MIME type, size, modified timestamp).
- Reconnect, refresh or disconnect without viewing/storing provider tokens in the browser.
- Detect a disabled/misconfigured registry with a clear operator-facing message.

This is **read-only connectivity and configuration**, not a full ingestion pipeline. The existing Semantic Store indexes a **server-selected local directory**, and does not yet have a tenant-isolated cloud source importer. **Never put one user's Google documents into a shared local Semantic Store.**

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
| `POST` | `/v1/drives/google/disconnect` | Deletes the local encrypted credential; attempts remote Google token revocation |

The OAuth callback is the only route not requiring a bearer token. It consumes a cryptographically random 10-minute, single-use server-side state and uses a PKCE code verifier. No access/refresh tokens are returned to Studio. On callback failure, no credential is stored and the user sees a generic failure URL.

### Storage boundary

Every user's provider token and folder selection is encrypted in a separate AES-256-GCM payload, with associated data binding the token to the verified OIDC subject. The on-disk lookup key is the SHA-256 digest of that subject. Storage is a local file with restrictive permissions, and the encryption key is configured **out of band**. All Google API requests run from the registry; the browser cannot send arbitrary Google API URLs.

This is appropriate for a **local single-instance research prototype**, not for public multi-tenant durability or regulatory assurance. It still needs a proper secret manager, database isolation, backoff/rate limits, stronger OAuth/CSRF hardening, signed user-session UX, backup/recovery, token lifecycle and retention reviews before production.

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

No live Google OAuth end-to-end test has been completed without project-specific client credentials and a verified consent screen.

## Next production milestones

1. Implement actual OIDC sign-in/refresh for Studio instead of manually supplied bearer tokens.
2. Replace account-wide `drive.readonly` with Google Picker + `drive.file` if buyer permission requirements demand file-specific grants.
3. Add genuinely user-isolated source importer and background sync with revocation/deletion semantics; the existing local Semantic Store worker **must not** be reused as a multi-user destination without isolation.
4. Offer Microsoft OneDrive and Dropbox through matching per-user OAuth adapters after comparable security reviews.
5. Connect authorized imported source lineage and tenant-bound indices to Evidence Assurance; never infer provenance independence from multiple uploaded files.
