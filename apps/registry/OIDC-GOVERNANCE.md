# Registry governance: OIDC identity, RBAC and independent approval

**Research lineage:** Cyrille Eloundou — https://apx.guide/.

This increment adds **cryptographically verified OIDC JWTs**, scoped action permissions, and three-identity separation for signed PackSpec promotions. It remains a **single-process local-file registry**, not a production high-availability transactional governance service.

## Configure

The registry continues to support the existing local single-token development mode. To require authenticated roles, supply:

```bash
export QUALITYRAG_AUTH_MODE=oidc
export QUALITYRAG_OIDC_ISSUER=https://identity.example/realms/governance
export QUALITYRAG_OIDC_AUDIENCE=qualityrag-registry
export QUALITYRAG_OIDC_JWKS_URI=https://identity.example/realms/governance/protocol/openid-connect/certs
export QUALITYRAG_OIDC_ROLE_CLAIM=roles
export QUALITYRAG_POLICY_KEYS_FILE=/etc/qualityrag/trusted-policy-keys.json
npm --prefix apps/registry install
npm --prefix apps/registry start
```

This is **an example IdP URL**, not a hosted service. Your issuer must actually mint JWT access tokens containing the configured audience, `sub`, `iat`, `exp`, and a string-array `roles` claim. The registry verifies JWT signatures using the provider's JWKS, issuer, audience, allowed algorithms, token lifetime and expiry. Do not place access tokens in repo files.

| Role claim | API permission |
| --- | --- |
| `policy.reader` | Read registry state, resolved unsigned and signed policy |
| `policy.author` | Register service, create draft and stage externally signed policy |
| `policy.approver` | Approve draft or staged policy |
| `policy.publisher` | Publish approved signed policy or bind legacy policy |

**Identity separation:** Signed promotions require distinct `iss#sub` identities for staging, approval and publishing. Merely possessing every role does not allow self-approval or publishing one's own staged version. Unsigned drafts also block author self-approval in OIDC mode. In local single-token development mode, this separation is not enabled.

## Audit records

Each signed promotion transition creates a timestamped actor/event record and a SHA-256 predecessor chain. The registry checks the stored chain and head on startup, rejecting inconsistent modified records. **This is an integrity check, not a digital signature or external ledger anchor**: an attacker with write access to the entire state file can rewrite and rehash it. Place the state file on controlled durable storage and export audit records to an independently managed system before production.

## Studio

The Studio interface accepts an OIDC bearer token entered by the operator and sends it to the registry; role enforcement occurs in the registry, not in React. Studio **does not provide an OIDC authorization-code/PKCE login** in this increment. Operators must obtain scoped tokens from their organization's existing IdP and switch tokens when performing distinct duties.

## Verification

```bash
npm --prefix apps/registry install
npm --prefix apps/registry test
```

Tests create a local OIDC JWKS endpoint and cryptographically signed RSA JWTs, verify wrong audience and missing-role rejection, require three real identities to publish a signed policy, reject self-approval even with multiple roles, and detect tampering with chained audit records.

## Production boundary

Not yet implemented: interactive browser OIDC login, service account policies, tenant isolation, managed key lifecycle, revocation/suspension guarantees, durable multi-writer transactions, distributed audit anchoring, key rotation runbooks, distributed policy promotion locks, or infrastructure deployment. **Running multiple registry processes on one JSON file is unsupported**. OIDC authorization verifies an identity and its claims but does not prove that the original APX PackSpec is complete or that evidence content is true.
