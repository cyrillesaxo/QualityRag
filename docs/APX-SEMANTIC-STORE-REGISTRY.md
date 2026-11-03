# APX Semantic Store — canonical registry and integration boundary
Status: IMPLEMENTATION PROPOSAL / source audit 2026-11-03. This document is not a production-readiness assertion.

## Grounded repository findings
- `apx/packages/apx-hcr/src/index.ts`: `recoverConstraintFiber`; finite registered hypothesis family, authority-licensed evidence, probe ranking; model-relative identification only.
- `apx/packages/apx-rcoc/src/index.ts`: `compareSemanticAssuranceSnapshots`; G1–G12 coordinate movement, witness-group change, TERM status change, ordered-trace qualification.
- `apx/packages/apx-epistemic/README.md`: six skills, including gap frontier, Ladder bridge and fresh-transfer admission; explicitly does not infer truth from raw prose.
- `apx/docs/data-assurance/REUSE_MATRIX.md`: reusable `@apx/regime`, `@apx/evidence`, `@apx/wbc`, `@apx/pack-spec`; warns complete HCR/RCOC/TERM/15-cell integration is not migrated.
- `QualityRag/tools/packspec_compiler/typed_ir.py`: reviewed source-derived ConstraintIR, partial metadata projection, deferred/limited temporal/authority/probe/predicate semantics.
- `QualityRag/docs/ADR-0001-semantic-constraint-compiler.md`: proposed semantic compiler architecture, not existing end-to-end implementation.

## Registry
| Concept | Canonical source / planned binding | Store role | Verification status |
|---|---|---|---|
| KnowledgeIR | NEW, interoperates with existing ConstraintIR | source-grounded semantic node/edge representation | PROPOSED |
| 12G | `@apx/rcoc` canonical taxonomy | typed semantic coordinates | CODE FOUND; cross-repo parity pending |
| WitnessGraph / D15 | `@apx/evidence`, ICEBERG references | source/dependency/contradiction provenance | REUSE CANDIDATE; parity pending |
| WBC / W_min | `@apx/wbc` | protected-verdict-preserving projection | REUSE CANDIDATE; parity pending |
| RCT | `@apx/regime` | bounded regime admission | EXTRACTED PER APX REUSE MATRIX |
| FF-RCT | APX research / semantic-source-spans references | source-to-regime structure and bounded transition | CANONICAL EXECUTABLE CONTRACT NOT YET VERIFIED |
| FFI-RCT | APX research references | forensic/regime conjunction | CANONICAL CONTRACT NOT YET VERIFIED |
| HCR | `@apx/hcr` | compatible hypothesis fiber + ranked probes | EXECUTABLE SOURCE FOUND |
| FFI | QualityRag example policies; APX research | unknown-gap/deception investigation | PARTIAL/PROJECTION ONLY in QualityRag |
| RCOC | `@apx/rcoc` | G-vector and receipt-to-receipt changes | EXECUTABLE SOURCE FOUND; not full transformation proof |
| TERM | APX references in RCOC and reuse matrix | scenario replay/invalidation | INTEGRATION PARITY PENDING |
| KBCT | APX bounded cost/clock model | bounded verification work | INTERFACE TO VERIFY |
| First Bite / Question Fan | APX/ICEBERG, QualityRag examples | ranked discriminating questions | REUSE CANDIDATE |
| Fractal Focus / ICEBERG | ICEBERG and APX references | multiscale obligation exposure | REUSE CANDIDATE |
| PackSpec | QualityRag SDKs, `@apx/pack-spec` | version-pinned admission obligations | METADATA GATE IMPLEMENTED; full semantic parity pending |
| Ladder | `@apx/epistemic` | learning/re-derivation projection | CODE/DOC FOUND |
| Witness receipts | `@apx/receipts` | auditable proof obligations | REUSE CANDIDATE |

**No inferred aliases:** semantic 12G, security G overlays, KBCT K/B/C/T and any unrelated K/B/C/T axes must not be silently merged. FF-RCT and FFI-RCT are unresolved integration contracts, not fabricated APIs.

## Design invariants
1. Original source fingerprint + immutable source version preserved for every semantic object.
2. KnowledgeGraph meaning edges and WitnessGraph provenance edges link by stable object/version identity.
3. An embedding is a rebuildable index, never canonical evidence.
4. A derivation must bind source version, transformation kind, PackSpec digest and declared protected obligations.
5. A `PASS`/SAT for a bounded check never asserts truth or open-world completeness.
6. `UNKNOWN` and unmeasured/deferred mandatory obligations cannot authorize publication/admission.
7. Shared-origin witnesses cannot be counted as independent.
8. Retain historical versions and invalidate derived views when a referenced source, contract or witness changes.
9. Protect access to source objects *before* embedding, graph traversal, and evidence export; never promote secret text into a public receipt.
10. Provenance/authority claims cannot be inferred from a digest; require authenticated context.

## Execution order
SS-001 Canonical registry / records; SS-002 immutable source + object versions; SS-003 meaning/witness edge stores; SS-004 contract-bound admission gate; SS-005 WBC + RCOC adapters with cross-repo golden equivalence; SS-006 HCR probe frontier; SS-007 RCT/FF-RCT/FFI-RCT qualification after canonical API discovery; SS-008 TERM replay and KBCT budgets; SS-009 adversarial baseline versus vector and graph RAG.

## Minimum adversarial acceptance cases
- Copies of one upstream source never satisfy two-independent-origin policy.
- A derived summary omitting a mandatory prerequisite is REFUSE or INCONCLUSIVE, never ADMIT.
- Unknown source authority/time validity is INCONCLUSIVE.
- A stale source version invalidates its previously admitted projection.
- A falsely reported sequence cannot be inferred from two RCOC snapshots.
- HCR's sole surviving hypothesis without licensed support remains unconfirmed.
- A WBC projection can claim preservation only for an explicitly enumerated protected question set.
- FF-RCT or FFI-RCT with missing canonical runtime must remain DEFERRED.
