# Software story verification

**All 32 software candidates pass the written software criteria within their stated research-reference scope.** With US-001 and US-002 previously accepted, **34 stories have accepted or verified software evidence; 17 retain specific input, document or human-review requirements.**

This is source review and executable software evidence, not independent scientific/domain validation, a merge or production authorization. Formal ledger statuses are unchanged and must not be presented as 49 unimplemented stories.

| State | Stories |
|---|---:|
| Previously formally accepted | 2 |
| Software verification passed | 32 |
| Software candidates with unmet criteria | 0 |
| External input or merge required | 11 |
| Explicit human review required | 4 |
| Document checks remaining | 2 |
| Total | 51 |

## Evidence

Tested immutable commit: [`3484f2575deda90b9d9a591b480332cee67456d9`](https://github.com/cyrillesaxo/QualityRag/commit/3484f2575deda90b9d9a591b480332cee67456d9). **All 23 CI runs passed.** [Activation push run, attempt 2](https://github.com/cyrillesaxo/QualityRag/actions/runs/42030159671) passed **411 tests without skips**: 322 runtime (including Chromium/PostgreSQL), 24 TypeScript, 10 finite activation, 40 compiler and 15 ledger. The first push attempt timed out downloading Ubuntu media packages before testing; the identical commit passed on retry. The pull-request activation run also passed.

The [machine-readable report](SOFTWARE-VERIFICATION.json) contains all 128 criteria, exact test references, source module hashes, tested commit, inventory/map hashes and all 23 CI run identities.

## Gaps closed since the prior verification

The prior verification at `d78d9fb0f5e9c30077928cdddff08cd00fa4a1e7` passed 30 candidates and left US-033/US-038 incomplete. Six new checks now exercise their missing software behavior:

- **US-033:** actual signed-segment and AV1 decoders feed the same bounded frame queue at the same cadence. Startup, queue-empty wait time, rebuffer events and seeks are measured. A deliberately late producer proves real stalls are recorded. Frame hashes qualify the video comparison. This is local bounded playback; WAN/physical-device performance remains unmeasured.
- **US-038:** all six roles return explicit patches, rationale and parent grammar hash. Workers recompute evaluator-code, schema, runtime and exact task-dataset pins before sandbox execution. Changed task input or any stale code pin is rejected; the parent verifies the returned binding. This is deterministic task evaluation, not external-corpus or semantic-truth validation.

Implementation, API usage and boundaries: [Software gap closure](SOFTWARE-GAP-CLOSURE.md).

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
| US-033 | Streaming segment delivery and seek |
| US-034 | Append-only conversation tree |
| US-035 | Dialectical operations and reversible pruning |
| US-036 | Evidence-state separation and Research Ledger link |
| US-037 | Gardener proposal loop and review UI |
| US-038 | Isolated agent experiment harness |
| US-039 | Dedicated agent roles |
| US-040 | Adversarial evolution and held-out gates |
| US-042 | Pareto promotion and resource scheduler |
| US-043 | Tenant isolation and source authority |
| US-044 | Signed artifact and anti-replay pipeline |
| US-045 | SDK and CLI parity |

## Remaining requirements

The other 17 stories are 11 external-input/merge stories, four with explicit human-review criteria, and two documentation-check stories. The 32 software results support criterion-scoped software acceptance; they do not fabricate an independent signature or waive another story's explicit requirements. Formal ledger closure remains a separate recorded operation.
