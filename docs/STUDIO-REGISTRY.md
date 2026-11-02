# QualityRag Studio + Service Registry (local development prototype)

This is an **APX-inspired extraction**, not a wholesale copy of APX Dashboard. The APX source audit found `apps/dashboard/src/pages/AIStudio.tsx` depends on an APX CLI and runner, `PluginStudio.tsx` contains demonstration-only actions, and `apps/registry/src/index.js` is a local-file index stub. The stronger reusable admission concept is APX `apps/data-assurance/src/constraint-registry.ts`: bind a constraint to approved authority/version/fingerprint and fail when it diverges.

## Run

Requires Node.js 20 or later. In two terminals:

```sh
export QUALITYRAG_REGISTRY_TOKEN='use-a-long-random-local-token'
npm --prefix apps/registry start
```

```sh
cd apps/studio
npm install
npm run dev
```

Open `http://127.0.0.1:5173`; enter the registry token from the first terminal.

## Workflow

1. Register a service identity.
2. Draft a PackSpec JSON document; the registry records a SHA-256 fingerprint and rejects overwrites.
3. Approve that immutable policy version (experimental single-key operator approval).
4. Bind an approved revision to service + environment.
5. Resolve `GET /v1/resolve/:service/:environment` and enforce its policy with the application's SDK.

The registry persists to `.qualityrag/registry.json` by default, with atomic replacement. Do not commit this file. No central registry is involved in individual SDK evaluations.

## API

- `GET /health` public
- `GET /v1/state` operator-only
- `POST /v1/services` body `{id, displayName}`
- `POST /v1/policies/drafts` body PackSpec
- `POST /v1/policies/:id/:version/approve`
- `POST /v1/bindings` body `{serviceId,environment,policyId,version}`
- `GET /v1/resolve/:service/:environment` returns approved policy, fingerprint, service/environment

All `/v1` endpoints require `Authorization: Bearer <QUALITYRAG_REGISTRY_TOKEN>`. By default the registry binds to loopback only.

## Important limitations before deployment

This is a **local developer prototype**, not a production policy control plane. A shared operator token is not per-service authentication or RBAC. No OIDC, TLS termination, tenant isolation, multi-instance concurrency, cryptographic signatures, rollout/rollback workflow, audit immutability, policy cache/TTL or SDK remote-policy bootstrap is implemented. Do not expose the registry or Studio to the public internet. Production enforcement must fail closed on missing/unverified policies. APX code was reviewed for design lineage; do not assume its CLI or private infrastructure is available here.

## Tests

```sh
npm --prefix apps/registry test
cd apps/studio && npm install && npm run build
```
