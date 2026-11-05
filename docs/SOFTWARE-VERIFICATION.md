# Software story verification

Verification is complete for the 32 software-complete candidates. **30 pass the software acceptance checks; US-033 and US-038 remain incomplete.**

This is source review and executable software evidence, not independent domain validation, merge acceptance or production authorization. The formal ledger remains unchanged; it must not be interpreted as 49 unimplemented stories.

| State | Stories |
|---|---:|
| Previously formally accepted | 2 |
| Software verification passed in this review | 30 |
| Software candidates with unmet criteria | 2 |
| External input or merge required | 11 |
| Explicit human review required | 4 |
| Document checks remaining | 2 |
| Total | 51 |

## Evidence

Tested immutable commit: [`d78d9fb0f5e9c30077928cdddff08cd00fa4a1e7`](https://github.com/cyrillesaxo/QualityRag/commit/d78d9fb0f5e9c30077928cdddff08cd00fa4a1e7). All 23 GitHub Actions runs passed. [Activation push run](https://github.com/cyrillesaxo/QualityRag/actions/runs/42028091319) passed **405 tests without skips**: 316 runtime (including actual Chromium and PostgreSQL), 24 TypeScript, 10 finite activation, 40 compiler and 15 ledger.

Four additional checks exercise actual encoder bytes/model/time/fallback measurements; finite interpreter code-option and work-bound refusal; a reproducible counterexample tied to its violated field/clause; and the documented key lifecycle/version floor. Finite DSL isolation is not a claim of arbitrary-code process isolation.

[Machine-readable report](SOFTWARE-VERIFICATION.json) includes all 128 candidate criteria, exact test references, implementation module hashes, tested commit, source-inventory/map hashes and the 23 CI run identities.

## Passed software verification

| Story | Feature |
|---|---|
| US-003 | Independently replayable research harness |
| US-005 | Purpose-scoped information obligations |
| US-006 | ConstraintIR-to-activation binding |
| US-008 | Omission and residual audit |
| US-010 | RCT typed grammar integration |
| US-011 | SAT/UNSAT/UNKNOWN semantics |
| US-012 | Purpose-preserving regime transition |
| US-013 | RCT candidate search with early stopping |
| US-014 | Constraint compilation and reusable decisions |
| US-015 | Finite equivalence proof and counterexamples |
| US-016 | Typed semantic intermediate representation |
| US-017 | Exact information and reversible source custody |
| US-018 | Source adapters (text, PDF, HTML, CSV/SQL) |
| US-019 | Review-gated relation and role extraction |
| US-020 | Reusable grammar registry and dependency DAG |
| US-023 | Executable finite ACTIVATE/VERIFY/FALLBACK |
| US-024 | Model and grammar compatibility manifest |
| US-026 | Deterministic finite reconstruction |
| US-030 | Shared grammar video encoder prototype |
| US-032 | Model amortization and catalog economics |
| US-034 | Append-only conversation tree |
| US-035 | Dialectical operations and reversible pruning |
| US-036 | Evidence-state separation and Research Ledger link |
| US-037 | Gardener proposal loop and review UI |
| US-039 | Dedicated agent roles |
| US-040 | Adversarial evolution and held-out gates |
| US-042 | Pareto promotion and resource scheduler |
| US-043 | Tenant isolation and source authority |
| US-044 | Signed artifact and anti-replay pipeline |
| US-045 | SDK and CLI parity |

## Unmet criteria

| Story | Criterion | Finding |
|---|---|---|
| US-033 | 4 | Verification found startup/seek timings only. benchmark_seek explicitly returns network_buffering=UNMEASURED; full criterion is not met. |
| US-038 | 2 | The cited check proves parent hash, patches and rationale for grammar-compiler only. Other role proposals do not uniformly carry patches; every-proposal criterion is not yet established. |
| US-038 | 4 | Worker requests bind parent grammar and task, but neither worker nor evaluation currently enforces a pinned evaluator-code identity and dataset manifest. Passing CI is not that runtime binding. |

US-033 currently measures cold local seek against a fresh FFmpeg process; it explicitly labels network buffering UNMEASURED. US-038 has parent/task bindings and a real syscall sandbox, but that does not establish the missing every-proposal patch contract or pinned evaluator-code/dataset contract. These limitations were not waived.

## Remaining acceptance

The 30 software results can support criterion-scoped software acceptance. They do not fabricate an independent signature or silently satisfy explicit external requirements. Including the two previously accepted stories, **32 have accepted or verified software evidence; 19 still have specific verification, input or review requirements**. Formal ledger closure is a separate recorded operation.
