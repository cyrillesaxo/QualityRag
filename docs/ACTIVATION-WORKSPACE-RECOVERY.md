# Activation implementation recovery checkpoint

Date: 2026-11-04. Task: complete the 51 stories in FR.MD.

## Interruption and delivery boundary

The execution workspace became unavailable after local implementation and tests,
before the latest source changes could be committed. GitHub remains reachable,
but the coding filesystem and shell are not reachable. This checkpoint preserves
the recovery state; it does not deliver the uncommitted implementation.

Last committed implementation: c7fa4325c4a23486cecf7968f25c0c5ff54e8906
Branch: docs/activation-research-fr-v01
Pull request: https://github.com/cyrillesaxo/QualityRag/pull/70

The branch still contains the earlier foundation. Do not describe the following
local changes as pushed, merged, independently accepted, or covered by remote CI.

## Last observed local verification

- Full activation runtime suite: 65 tests, all passed, with the real Chromium
  workflow and pinned original APX source tests enabled.
- TypeScript SDK build and existing SDK suite: 18 tests, all passed.
- Research Ledger suite after its signed-validation extension: 8 passed and
  3 real-PostgreSQL tests explicitly skipped because no test DSN was configured.
- Authored codec experiment ran actual encoding/decoding and retained a negative
  result: the palette/residual reference was larger than lossless AV1.
- These are observations from the interrupted local run, not commit-bound CI.
  Source hashes and final export need to be rechecked after filesystem recovery.

## Local changes to recover

Relative to the working repository root, inspect before overwriting anything:

- tools/activation_runtime/scene_codec.py: actual frame ingestion, shared palette,
  exact residuals, playable reconstruction, source PTS/audio checks, and scalar/
  strided decoder variants.
- preservation.py, adapters.py, interpreter.py: domain obligations, exact anchors,
  PDF/text/CSV adapters, actual finite operator execution, checked fallback,
  exhaustive graph comparisons and signed ConstraintIR bindings.
- authority.py, device.py, streaming.py: authenticated principals, independent
  signed review, resumable updates, sparse compilation, signed decoder/model/
  index, seeking, pause/resume, representation switches and fallback.
- agents.py, agent_worker.py, process_sandbox.py, rct_worker.py, search.py,
  decode_worker.py, roles/: six schema-constrained deterministic research roles
  and hard syscall/CPU/memory/time restrictions.
- gardener.py, proposals.py, service.py, web/, bootstrap.py: append-only review
  workflow, periodic authorized proposals, feedback metrics, source upload,
  branch search, preview, pruning/reopening, and local authenticated service.
- experiments.py, adversaries.py, neural_baseline.py, pilot.py, release.py:
  preregistration, hidden-family gates, three actual codec arms, offline pinned
  neural adapter, device telemetry and independent signed release conditions.
- ledger_validation.py and tools/research_ledger/ledger.py: scope-bounded signed
  validation through the canonical ledger. No unverified VALIDATED promotion.
- fixture_catalog.py, fixtures/, profile_fixtures.py, profiles/, cli.py,
  run_research.py, research/: domain fixtures, one-command experiments, primary
  prior-art register, environment lock, receipts, paper and figures.
- sdk/python/qualityrag_activation/__init__.py
- sdk/typescript/src/activation.ts, src/index.ts and package-lock.json
- tests/: the full 65-test suite, including real browser source creation and
  review actions, source/tenant isolation, SDK HTTP parity, codec corruption,
  signed review/replay, sandbox denial and actual playable video.

## Recovery sequence

1. Recover the original working tree; do not reset it to the earlier branch.
2. Inspect local source and test receipts, and compare to the committed base.
3. Finish the FR.MD current-status update and CI workflow. Preserve the original
   51 IDs and acceptance criteria; do not weaken them to manufacture completion.
4. Regenerate capabilities.json fingerprints after any source/criteria edit.
   The local draft classified 37 stories IN_REVIEW and 14 BLOCKED, with no DONE.
   Those draft counts are not the authoritative committed backlog.
5. Rerun appropriate checks, stage only intended source/tests/receipts, and
   commit/push using an expected-head lease. Exclude node_modules, caches and
   development private keys/access tokens.
6. Observe actual remote CI and review before merging.

## Genuine acceptance gates

No authored fixture, demo signature or passing software test supplies:
a representative independently reviewed licensed 100-clip corpus; licensed
neural weights and a qualified matched-fidelity run; two physical mobile/TV
device measurements; independent clinical/legal/video adjudication; canonical
FF-RCT reconstruction parity; or independent release/merge acceptance.

The reference codec is a bounded palette predictor, not a learned semantic model
or a renamed claim of FF-RCT. Retain its negative AV1 comparison. All 51 stories
must remain subject to their actual acceptance evidence.
