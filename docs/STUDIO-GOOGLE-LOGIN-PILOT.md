# QualityRAG Studio pilot — Google login

Google identity and Google Drive access are **separate OAuth grants**. Signing into Studio does not grant Drive read access or a QualityRAG reviewer role.

## Current rollout

The static Studio includes a login page with **Continue with Google**. The control remains disabled until a trusted public-client OIDC identity provider has been configured with Google as its upstream identity source. A Google ID token is **not** accepted as a Registry token. A successful login must return a short-lived **QualityRAG audience-scoped access token** from the configured OIDC provider, with server-issued roles and exact `qualityrag_services` claims.

The public React login is not an access control for the published JavaScript assets. All data/API authorization belongs in the secure Registry. Do not expose Registry on a public unprotected host, put client secrets in `VITE_*` variables, or send customer documents during a smoke test.

## Required frontend build configuration (Netlify project, Builds scope)

- `VITE_QUALITYRAG_OIDC_CLIENT_ID` — **public** client ID, not a Google client secret
- `VITE_QUALITYRAG_OIDC_AUTHORIZATION_ENDPOINT` — trusted HTTPS OIDC provider authorize endpoint
- `VITE_QUALITYRAG_OIDC_TOKEN_ENDPOINT` — corresponding HTTPS token endpoint on the same origin
- `VITE_QUALITYRAG_OIDC_AUDIENCE` — audience configured on the provider for the Registry
- `VITE_QUALITYRAG_ALLOW_MANUAL_TOKEN` — leave **unset**; enabling diagnostic manual tokens is not a normal customer login flow

The provider must permit the **Authorization Code + PKCE S256** public-client flow, token endpoint browser CORS to the Studio origin, `openid profile email` scopes, and this exact registered callback:

`https://marvelous-griffin-ee3535.netlify.app/`

Configure **Google as an upstream login identity at the provider** (for example, a properly configured Google social connection in an OIDC broker). Do not confuse the Google OAuth Client ID used for Google Drive with the OIDC public client configured for the Studio frontend.

The browser generates a cryptographic PKCE verifier and state, stores **only the short-lived exchange transaction** in tab session storage, validates the returned state, strips the authorization code from the browser URL, exchanges it for an access token, and verifies the token via a read-only Registry route. The access token stays **only in React memory** and is cleared on sign-out/reload; no automatic long-term refresh. Token redemption and role assignment remain the identity provider's responsibility.

## Backend requirements

- Separately reviewed same-origin HTTPS routing for `/ready` and `/v1/*` to the loopback-only Registry.
- Registry OIDC configured with the correct `QUALITYRAG_OIDC_ISSUER`, `QUALITYRAG_OIDC_AUDIENCE`, and `QUALITYRAG_OIDC_JWKS_URI`. The existing Registry accepts issuer-validated JWTs only, and checks exact role and service scopes.
- Provision OIDC roles such as `drive.reader` and `drive.manager` **outside the client**. Do not use Google email address as implicit authorization, and never grant all roles by default.
- Separately configured Google Drive API OAuth client with an approved callback on the authenticated Registry gateway, scoped owner-only credentials and explicit user consent.
- Independent security review before exposing an API gateway or changing firewall rules.

## Acceptance checks

1. With no OIDC provider configuration, Continue with Google is visible but disabled, and no token is requested.
2. With a configured provider, begin the Google-upstream login. A callback with missing/wrong/expired state or an unsupported duplicate code fails without granting a session.
3. A valid OIDC access token with no QualityRAG roles receives a Registry authorization failure, not access to customer data.
4. A valid limited role receives only that role's data and cannot read another service or owner's Drive index.
5. Reload and sign out clear the browser's in-memory token. A new sign-in is necessary.
6. Google Drive requires its own explicit consent before any sync. Confirm only the selected folder's eligible content is indexed.
7. Verify denial, revocation, audit, and A1–A7 against a non-sensitive self-pilot before declaring customer acceptance.

**The Netlify frontend build alone does not complete any of these live environment acceptance checks.**
