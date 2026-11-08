# QualityRAG Studio — Recorded Evidence Assurance (local integration)

**Status (2026-11-08):** Opt-in, local single-process registry telemetry with persisted append-only records, role-scoped API, deterministic metadata replay, authenticated reviewer dispositions, Studio read/replay/review UI and a Python SDK emitter. **Not a production multi-tenant observability or compliance system.**

> **Show, don't convince:** A customer can inspect an actual recorded evaluation, the declared PackSpec requirements, pseudonymous source/origin tokens, the deterministic verdict, and whether a same-server replay reproduces it. An authorized, separate reviewer can append an acceptance or dispute. There is no guarantee the declared source lineage is authentic or that the governing contract was complete.

## Architecture: present and absent

| Component | Present | Not yet present |
|---|---|---|
| Evaluations | Approved service/environment PackSpec resolved server-side; no client-supplied verdict | Automatic evaluation capture from every production application |
| Telemetry | Explicit opt-in `POST /v1/evidence/evaluations`, 0–100 metadata evidence rows, 50-row paged-style display cap | Coverage denominator, OTel pipelines, batch delivery, dedup across collectors |
| Storage | Local 0600 JSONL file; sequence/previous-hash verification on load/read; fsync on append | Postgres tenant isolation, external anchoring, retention/deletion service, distributed writers |
| Security | OIDC `evidence.ingest`, `evidence.reader`, `evidence.reviewer` roles; required signed `qualityrag_services` scope such as `claims-api@dev`; local developer token fallback | Independent source custody, encryption-at-rest management, deployed identity UX |
| Replay | Re-evaluates **stored** approved policy, source metadata and timestamp using the same registry JS gate | Independent verifier and original-source-content authentication |
| Customer review | Separate OIDC actor, server-authoritative status, immutable append-only disposition history | Digital review signatures, customer IdP provisioning, appeal/adjudication workflow |
| Studio | Real events panel next to synthetic explanatory lab; manual refresh, inspector, replay, disposition, unsigned export | Live streaming and multi-service analytics |
| SDK | Explicit Python emission helper; no automatic background traffic | Java/TS native emitters and strong cross-version parity evidence |

**Important:** the current registry evaluator is a bounded JavaScript metadata gate matching core v0.1 decision semantics. Its results should be tested for parity with each consuming SDK before client acceptance testing; do not claim exhaustive parity. The registry origin fields are caller-declared, not independently verified. The ledger hash chain is *tamper-evident under restricted file access*, not tamper-proof against a privileged actor who can rewrite all state and hashes.

## Running the local prototype

Requires Node.js 20+, Python 3.12+ and the registry/Studio dependencies.

```sh
export QUALITYRAG_REGISTRY_TOKEN='use-a-long-random-local-development-token'
export QUALITYRAG_EVIDENCE_LEDGER_FILE="$PWD/.qualityrag/evidence.jsonl"
npm --prefix apps/registry install
npm --prefix apps/registry start
```

In a second terminal:

```sh
npm --prefix apps/studio install
npm --prefix apps/studio run dev
```

Open `http://127.0.0.1:5173`. Use Studio to register a service, create/approve a PackSpec, and bind it to a service/environment, then open **Recorded Evidence Assurance** after connecting. The ledger is *disabled* unless `QUALITYRAG_EVIDENCE_LEDGER_FILE` is set. No records appear until an application explicitly emits them.

### Send a source-minimized real event through Python

This example uses **synthetic opaque tokens**. The operator must already have a bound approved PackSpec containing `governing-rule`. A local development bearer token can ingest and read, but cannot independently approve its own observations. Production acceptance requires separate OIDC identities.

```python
from qualityrag.telemetry import emit_evidence

event = emit_evidence(
    "http://127.0.0.1:5055",
    "DEVELOPMENT_REGISTRY_TOKEN",
    service_id="claims-api",
    environment="dev",
    request_id="request-0001",
    trace_id="trace-0001",
    evidence=[
        {
            "id": "ev_" + "1"*32,
            "requirement_id": "governing-rule",
            "origin": "org_" + "a"*32,
            "source_ref": "src_" + "b"*32,
            "status": "SUPPORTS",
            "observed_at": "2026-11-08T16:56:00.000Z",
        }
    ],
)
print(event["id"], event["verdict"])
```

Use the **current actual UTC evidence-observation time** for freshness-constrained policies. Do not generate source tokens by blindly hashing raw IDs with low entropy; create opaque, purpose-scoped handles in trusted ingestion infrastructure. Never send original PDFs, prompts, customer names, email addresses, PAN, retrieved snippets or secrets. A policy's requirement IDs are governed configuration and may themselves be sensitive; do not store secret values there.

### OIDC requirements for customer telemetry

A signed identity token must contain the correct configured issuer/audience and:

```json
{
  "roles": ["evidence.reader", "evidence.reviewer"],
  "qualityrag_services": ["claims-api@dev"]
}
```

The `qualityrag_services` array is required for every evidence API in OIDC mode, including when the subject possesses a role. Separate service writer identity (`evidence.ingest`) from independent customer reviewer identity (`evidence.reviewer`). A reviewer cannot review an evaluation emitted under the same OIDC subject, even if they possess all roles. The local single-token mode is **not** a substitute for independent acceptance.

### Registry API

| Request | Role | Meaning |
|---|---|---|
| `POST /v1/evidence/evaluations` | `evidence.ingest` | Send metadata and reference a bound approved policy; server calculates verdict. Request IDs are idempotent within service/environment. |
| `GET /v1/evidence/evaluations?serviceId=claims-api&environment=dev` | `evidence.reader` | Return up to 50 recent records and observed total; eligible request coverage remains unknown. |
| `GET /v1/evidence/evaluations/{id}` | `evidence.reader` | Inspect a scoped record and its review history. |
| `POST /v1/evidence/evaluations/{id}/replay` | `evidence.reader` | Re-evaluate pinned policy, metadata and original evaluation time. |
| `POST /v1/evidence/evaluations/{id}/reviews` | `evidence.reviewer` | Append `ACCEPTED` or `DISPUTED` with required reason code and optional safe note. |

Review reason codes: `REPRODUCED`, `FALSE_BLOCK`, `PROVENANCE_UNVERIFIED`, `POLICY_DISAGREEMENT`, `OTHER`. Customer review is a **disposition on a finding**, not a change to the deterministic engine verdict.

### Tests

```sh
npm --prefix apps/registry test
npm --prefix apps/studio run build
PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests
```

The registry tests exercise HTTP role separation, scoped access, idempotency, duplicate-origin refusal/inconclusive logic, deterministic replay, customer disposition and stored-ledger tampering. Python tests verify transport, metadata allow-lists and non-TLS restrictions.

## Production acceptance gates — do not conflate implementation with readiness

1. Tenant-aware durable database with RLS and per-service authentication, migration and recovery tests.
2. Pseudonymous token governance, retention, deletion, encrypted storage and independent security review.
3. Authenticated custody for source-origin assertions and reviewer identities; avoid treating mere digest strings as proof.
4. Client-side event instrumentation for **eligible request denominator** and evidence requirements not evaluated.
5. Cross-language parity on pinned versions and independent reproduction of critical findings on customer-approved fixtures.
6. Reviewer acceptance workflow with strong external audit anchoring or trusted signing where contractually required.
7. Production IAM, rate limits, throughput, disaster recovery, drift/version handling and trace export.
8. Explicit buyer acceptance experiment proving reviewer effort and false-block tradeoffs are acceptable.

**Do not label a customer review or a same-server replay as a regulatory compliance certificate or mathematically proven truth.** A missing telemetry event remains an unknown, never an `ADMIT`.
