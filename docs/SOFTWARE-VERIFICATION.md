# Software and documentation verification

**System-scope correction:** the counts below are historical component
verification, not proof of an autonomous, continuously improving Semantic
Garden. The intended outcome requires a persistent RCT research loop that
evolves grammar and activation together. See [continuous RCT Garden](CONTINUOUS-RCT-GARDEN.md)
for its implementation and the explicit remaining live-model/research limits.

**37 stories have accepted or verified software/documentation evidence: two previously accepted, 33 software-verification passes and two documentation-verification passes. Fourteen stories retain additional work or evidence requirements.**

This is source review and executable software/documentation evidence, not independent scientific/domain validation, a merge or production authorization. Formal ledger statuses remain separate: 2 DONE, 36 IN_REVIEW, 13 BLOCKED. They must not be presented as 49 unimplemented stories.

| State | Stories |
|---|---:|
| Previously formally accepted | 2 |
| Software verification passed | 33 |
| Documentation verification passed | 2 |
| Remaining requirements | 14 |
| Total | 51 |

## Evidence

Tested immutable commit: [`4fde137d8e19bd2e25944b437a4e559bc3db264c`](https://github.com/cyrillesaxo/QualityRag/commit/4fde137d8e19bd2e25944b437a4e559bc3db264c). All 23 CI runs passed. [Activation push run 42035039771](https://github.com/cyrillesaxo/QualityRag/actions/runs/42035039771) passed **419 tests without skips**: 330 runtime (including Chromium/PostgreSQL), 24 TypeScript, 10 finite activation, 40 compiler and 15 ledger.

[Machine-readable report](SOFTWARE-VERIFICATION.json) records all 140 verified criteria, test references, source hashes, source commit and CI runs, plus the explicit unverified criteria of each remaining story.

## New verification

- **US-004:** checked the six prior-art/comparator rows, dated/versioned references, no-priority boundary and negative-result register. This is a document check, not a positive independent novelty finding.
- **US-007:** integrated unmodified original APX WitnessGraph at the already pinned APX commit. Its Git blob matches upstream exactly. Actual canonical grouping is compared with declared custody-root components; missing/changed source or discrepancies refuse assessment and gate projection. [Scope and source identity](CANONICAL-WITNESS-GRAPH.md).
- **US-050:** added versioned proposal descriptions; made measured byte/frame claims depend on the input receipt; bound the traceability matrix to its SHA-256; regenerated Markdown, figures and PDF. Three regression checks prove byte-identical reproduction and that changed measurements cannot retain false fixed conclusions. The rendered four-page paper was inspected. Independent peer review is not claimed.

The earlier US-033/US-038 gap closures remain covered: [playback measurements and agent evaluation pins](SOFTWARE-GAP-CLOSURE.md).

## Verified stories

| Story | Feature | Verification |
|---|---|---|
| US-003 | Independently replayable research harness | software |
| US-004 | Risk, prior art and novelty register | documentation |
| US-005 | Purpose-scoped information obligations | software |
| US-006 | ConstraintIR-to-activation binding | software |
| US-007 | WitnessGraph and evidence independence | software |
| US-008 | Omission and residual audit | software |
| US-010 | RCT typed grammar integration | software |
| US-011 | SAT/UNSAT/UNKNOWN semantics | software |
| US-012 | Purpose-preserving regime transition | software |
| US-013 | RCT candidate search with early stopping | software |
| US-014 | Constraint compilation and reusable decisions | software |
| US-015 | Finite equivalence proof and counterexamples | software |
| US-016 | Typed semantic intermediate representation | software |
| US-017 | Exact information and reversible source custody | software |
| US-018 | Source adapters (text, PDF, HTML, CSV/SQL) | software |
| US-019 | Review-gated relation and role extraction | software |
| US-020 | Reusable grammar registry and dependency DAG | software |
| US-023 | Executable finite ACTIVATE/VERIFY/FALLBACK | software |
| US-024 | Model and grammar compatibility manifest | software |
| US-026 | Deterministic finite reconstruction | software |
| US-030 | Shared grammar video encoder prototype | software |
| US-032 | Model amortization and catalog economics | software |
| US-033 | Streaming segment delivery and seek | software |
| US-034 | Append-only conversation tree | software |
| US-035 | Dialectical operations and reversible pruning | software |
| US-036 | Evidence-state separation and Research Ledger link | software |
| US-037 | Gardener proposal loop and review UI | software |
| US-038 | Isolated agent experiment harness | software |
| US-039 | Dedicated agent roles | software |
| US-040 | Adversarial evolution and held-out gates | software |
| US-042 | Pareto promotion and resource scheduler | software |
| US-043 | Tenant isolation and source authority | software |
| US-044 | Signed artifact and anti-replay pipeline | software |
| US-045 | SDK and CLI parity | software |
| US-050 | Peer-review package and reproducible figures | documentation |

## Remaining stories

These stories have an external/merge or human-review requirement, and some also retain software criteria that are only IMPLEMENTED rather than independently exercised. Their category does not imply that all remaining work is outside the repository. No unverified criterion is silently accepted.

| Story | Feature | Unverified criteria |
|---|---|---|
| US-009 | Domain preservation profiles | 3 (human_review, needs_input) |
| US-021 | FF-RCT native-regime integration | 1 (external_input, needs_input), 2 (external_input, needs_input), 3 (software, implemented), 4 (external_input, needs_input) |
| US-022 | Activation grammar v0.1 baseline | 1 (merge, needs_input) |
| US-025 | Sparse activation and resource controls | 2 (external_input, needs_input) |
| US-027 | Device module updates and rollback | 4 (external_input, partial) |
| US-028 | Real audiovisual dataset and licensing | 1 (external_input, needs_input), 2 (external_input, needs_input), 3 (external_input, needs_input), 4 (external_input, needs_input) |
| US-029 | AV1 and learned-codec baselines | 1 (external_input, partial), 2 (external_input, needs_input), 3 (external_input, needs_input), 4 (external_input, needs_input) |
| US-031 | Frame/semantic/exact fidelity evaluation | 1 (human_review, needs_input), 2 (human_review, needs_input), 4 (software, implemented) |
| US-041 | Co-evolving encoder/decoder candidates | 1 (software, implemented), 2 (software, implemented), 4 (external_input, needs_input) |
| US-046 | Offline mobile/TV feasibility pilot | 1 (external_input, needs_input), 2 (external_input, needs_input), 4 (human_review, needs_input) |
| US-047 | Independent acceptance ledger | 1 (external_input, partial) |
| US-048 | Pre-registered controlled experiments | 1 (software, implemented), 2 (external_input, needs_input) |
| US-049 | Four worked real-world demonstrations | 4 (external_input, needs_input) |
| US-051 | Release readiness and pilot stop conditions | 1 (human_review, needs_input), 3 (external_input, needs_input) |

The evidence supports criterion-scoped software/documentation acceptance. Formal ledger closure is a separate recorded operation; no independent signature, licensing permission or physical measurement has been fabricated.
