# QualityRag Studio ↔ Semantic Garden engine (local development)

## What is actually connected

Studio's **Semantic Garden · Engine console** connects to a separate,
loopback-only Python research engine on **127.0.0.1:5057**. It is a third
connection in Studio alongside the policy registry (5055) and Semantic Store
directory workbench (5056). It does not replace either existing service.

Connection uses the operator-supplied **Garden bearer token** (not the registry
or semantic-workbench token). The browser connects through the existing Vite
development server's same-origin `/garden` proxy. The backend checks the
bearer token, allows only localhost Vite origins, and binds only to loopback.

- `GET /garden/status`: authenticated engine identity and live ledger-integrity
  check; disconnected/unhealthy states do **not** show as connected.
- `GET /garden/projection`: real branch/event/lineage view from the existing
  append-only QualityRag ledger, not fabricated fixture cards.
- `POST /garden/investigate`: invokes `run_controller` on supplied,
  bounded typed-graph training/evaluation inputs. It genuinely evaluates
  six grammar/activation combinations when examples uniquely identify
  an operator. Ambiguous investigations remain `NEEDS_ORACLE`.
- When `QUALITYRAG_GARDEN_RECEIPT_DIR` is configured, a successful bounded
  experiment writes a server-generated JSON receipt and adds an
  `INCONCLUSIVE` experiment claim to the existing research ledger.
  Receipt paths and ledger metadata are server-generated, never submitted
  by the browser.

The console does not automatically load synthetic results, connect to a
fake API, inherit registry authorizations, or offer production admission.

## Start locally

From the repository root:

```bash
mkdir -p .research/receipts
python tools/research_ledger/cli.py --db .research/progress.sqlite init

# Choose a long unique secret; never commit or copy it into frontend source.
export QUALITYRAG_GARDEN_TOKEN='replace-with-a-random-secret-at-least-24-chars'
export QUALITYRAG_RESEARCH_DB='.research/progress.sqlite'
export QUALITYRAG_GARDEN_RECEIPT_DIR='.research/receipts'

python tools/semantic_store/rct_garden_http.py
```

In a separate terminal:

```bash
cd apps/studio
npm install
npm run dev
```

Visit the local Vite URL, locate **6. Semantic Garden · Engine console**, enter
the **separate Garden token**, and click **Connect / refresh engine**.

The console must show a confirmed engine schema and valid ledger state before
it enables experiments. To investigate, paste JSON with precisely these
properties: `training`, `examples`, `source`, `revised_source`,
`workload`, `trials`, `max_probes`. Training/held-out source objects use
`rct.structured-ast/v1`; trials are 2–3; max probes 0–3.
This route cannot fetch authenticated external witnesses on its own.

## API smoke check

```bash
curl -fsS -H "Authorization: Bearer $QUALITYRAG_GARDEN_TOKEN" \
  http://127.0.0.1:5057/garden/status

curl -fsS -H "Authorization: Bearer $QUALITYRAG_GARDEN_TOKEN" \
  http://127.0.0.1:5057/garden/projection
```

Expected `status.schema`: `rct.garden-engine-status/v0.1`.
Expected `connected: true` and `ledger_integrity: CONSISTENT`.

A successful experiment returns `EVALUATED_UNVERIFIED`,
`ledger_persisted: true`, a `ledger_claim_id`, and
`qualityrag_admission: INCONCLUSIVE`. The receipt includes two
distinct SHA-256 values: `receipt_fingerprint` (canonical experiment
identity, excluding its fingerprint field) and `receipt_file_sha256`
(the exact SHA-256 of the persisted JSON artifact). The research ledger
stores the **file hash** as evidence content SHA and separately retains the
experiment fingerprint in metadata. Neither is a source-truth guarantee. If a receipt directory is not configured,
the controller may evaluate but reports `ledger_persisted: false`; it never
pretends that an unpersisted run is recorded.

## Automated regression checks

```bash
python -m unittest discover -s tools/semantic_store/tests \
  -p 'test_rct_garden_http.py' -v
python -m unittest discover -s tools/semantic_store/tests \
  -p 'test_rct_garden_projection.py' -v

cd apps/studio && npm run build
```

Tests exercise a **real HTTP server in-process**, bearer rejection, origin
restriction, actual bounded engine execution, content-addressed local
receipts, ledger projections and the no-admission boundary. The existing
Studio and Registry CI compiles the TypeScript UI. There is **no production
deployment or browser acceptance test** in this work.

## Critical trust and production limitations

- Local single-user developer interface. Do **not** expose port 5057 or the
  Vite proxy publicly. No tenant-scoped identity, HTTPS termination, or
  production-grade server hardening is implemented.
- Source references and external oracle labels are not authenticated. The
  Garden engine has no remote evidence oracle: ambiguous proposals cannot
  move past `NEEDS_ORACLE`.
- Receipts are local `file://` artifacts and serve as reproducible run
  records; they do **not** prove real-world source truth or independent
  scientific validation.
- The existing ledger API commits individual records separately; cross-row
  write atomicity and crash recovery need a canonical transaction upgrade.
- A source revision is a supplied typed graph; no continuous file watcher
  or autonomous scheduler is present.
- The existing APX console in the **separate apx repository** and the
  screenshot-specific Semantic Gardener UI were not modified or proven to
  be the same application as this QualityRag Studio console.
- This work does not replace canonical APX RCOC, HCR/FFI, WBC, TERM or D15
  engines, and does not claim native FF-RCT compression or new model ability.
- No model-generated claim can auto-promote a policy; admission remains
  `INCONCLUSIVE` under QualityRag governance.


## One-click engine execution acceptance

After connecting, select **Run engine self-test**. A passing response must
contain `rct.garden-engine-self-test/v0.1`, `status: PASS`,
`paired_candidates: 6`, `synthetic_test_only: true`, and
`qualityrag_admission: INCONCLUSIVE`. The console calls the actual
Python research controller through the same Vite proxy and bearer-token
boundary as real investigations. A failure disconnects the console.

```bash
curl -fsS -H "Authorization: Bearer $QUALITYRAG_GARDEN_TOKEN" \
  -H "Content-Type: application/json" -d '{}' \
  http://127.0.0.1:5057/garden/self-test
```

The self-test runs an actual bounded synthetic experiment but intentionally
does **not** write a scientific research claim into the ledger. It proves
a narrow localhost execution path, not production deployment, browser
acceptance, source authenticity, or agent capability expansion.

## Automated console-to-engine integration test

The dedicated GitHub Actions workflow
`.github/workflows/garden-console-connection.yml` now builds Studio,
starts the actual Python engine with an ephemeral SQLite research ledger
and bearer token, starts the Vite console on `127.0.0.1:5173`, then
makes live HTTP requests through the **Vite /garden proxy**.

`scripts/test-garden-console-connection.sh` checks authenticated
`/garden/status`, `/garden/projection`, `/garden/self-test`, and
explicit 401 rejection of incorrect bearer credentials. It verifies
that the engine executed six synthetic configurations and did not
promote or persist the smoke experiment.

This is a **cross-process console proxy acceptance test**, much stronger
than an isolated frontend build and backend unit test. It is not a
Playwright/browser UI automation test and cannot establish deployment
routing, real-user identity authorization, or production availability.

Run it locally from repository root after installing Studio dependencies:

```bash
bash scripts/test-garden-console-connection.sh
```
