# FR.MD — QualityRag Semantic Codex, RCT, PackSpec & Activation Grammar

> **Document:** Functional requirements, implementation plan, user stories and acceptance criteria  
> **Version:** 0.2 · **Date:** 2026-11-04 · **Owner:** APX / QualityRag research program  
> **Status:** Planning baseline; no story is complete merely because it appears here.  
> **Source of truth:** This backlog plus linked PRs, source files, independent test receipts and reviewer decisions.  
> **Research lineage:** Cyrille Eloundou · [apx.guide](https://apx.guide/)  
> **Repository:** [cyrillesaxo/QualityRag](https://github.com/cyrillesaxo/QualityRag)

## 0. The product and the falsifiable thesis

Create a **constraint-directed semantic representation system** in which a source is interpreted under a *purpose-specific PackSpec*, RCT evaluates candidate representation regimes, a versioned Semantic Codex grammar compiles reusable structure, and a local activation engine reconstructs only what the task requires. A Semantic Gardener and experimental agent population may propose grammar improvements; **no agent can self-certify semantic correctness or promote a decoder to production**.

The central hypothesis is **not** that semantic summaries are always smaller, nor that an LLM can losslessly recreate original footage. It is that *some workloads* admit economical, reusable, task-relative representations whose full lifecycle costs are lower than capability- and fidelity-matched alternatives. Every claimed saving must include compilation, model downloads, updates, encoding, residuals, local decoding, review, verification and energy when applicable.

**Non-negotiable invariants**

1. **Purpose before pruning:** Every omitted distinction is traced to a reviewed PackSpec clause and a declared purpose. Absence of a clause is not permission to discard source information.
2. **Separate structural SAT from truth:** Finite SAT/UNSAT/UNKNOWN is scoped to declared constraints; semantic/source admission remains INCONCLUSIVE without independent evidence and trusted authority.
3. **Immutable provenance:** Preserve original source bytes or lossless custody references, source/version hashes, transform graph, actor identity and independent witness origins.
4. **No invented precision:** A generative decoder may never silently fabricate exact captions, medical details, contractual roles, identities or timestamps.
5. **No perpetual recomputation by default:** RCT evaluates whether compilation, caching and activation save actual work; an inexpensive baseline may win.
6. **Reversible pruning:** Semantic Gardener deactivates or revises branches via append-only events, never erases research history.
7. **Fail closed:** Invalid schema, missing witness, stale policy, ambiguous grammar, incompatible model, budget exhaustion, unresolved preservation or unsupported device returns REFUSE/UNKNOWN/fallback, never an optimistic success.
8. **Do not conflate domains:** A conversation-memory grammar, a clinical terminology transition and a video decoder may share interfaces but do not share fidelity guarantees.

## 1. Verified starting point, not a completion claim

| Capability | Repository anchor | Current evidence / boundary |
|---|---|---|
| Typed bounded RCT grammar | `docs/RCT-TYPED-GRAMMAR-v1.4.md`, `tools/semantic_store/rct_typed_grammar.py` | Existing `EDGE/PATH/AND` generator with finite labels; no general semantic truth |
| RCT purpose and governance | `docs/RCT-END-TO-END-RESEARCH-DELIVERY.md`, `tools/semantic_store/rct_packspec_bridge.py` | Experimental finite structural checks and conservative QualityRag gate; no production semantic admission |
| Source-linked relation/role extraction | `docs/SEMANTIC-CODEX-RELATION-EXTRACTION-V1.2.md`, `docs/RCT-TYPED-ROLE-GRAMMAR.md` | Bounded candidates, exact anchors, signed-role research; not free-form general extraction |
| PackSpec compiler and reviewed ConstraintIR | `tools/packspec_compiler/TYPED-IR.md`, `tools/packspec_compiler/unified_gate.py` | Evidence metadata checks, deferred semantic operators, explicit limits |
| Existing training policy examples | `examples/apx-packspecs/policies/{ffi,semloan,question-fan,ffi-teacher}.json` | Concrete evidence-presence policies; not video preservation contracts |
| Semantic Store and Research Ledger | `tools/semantic_store/`, `tools/research_ledger/` | Candidate persistence, append-only research receipts and PostgreSQL adapter; no autonomous Semantic Gardener |
| Activation constraint prototype | [PR #69](https://github.com/cyrillesaxo/QualityRag/pull/69) | **Open PR at drafting:** bounded `PRESERVE/TRANSITION/ACTIVATE/VERIFY/FALLBACK` declarations, finite decisions and synthetic fixtures. Operators are **not executing video transformations**. Do not mark merged without checking |
| Codec, device playback, agent autonomy | Not established | Entirely proposed; no measured Netflix-scale or neural compression advantage |

**Status rules:** `DONE` requires merged reviewed code, reproducible tests and declared evidence; `IN_REVIEW` means a linked open PR; `PLANNED` means not delivered. Baseline stories below are **PLANNED** unless a cited merged implementation fully meets every criterion. PR #69 is **IN_REVIEW** as of the document date.

## 2. Formal system contract

For original information `X`, task `T`, reviewed preservation PackSpec `P`, candidate regime `R`, shared grammar `G`, compact payload `Z`, local activation policy `A`, residual `E` and reconstructed information `Xhat`, research:

```text
minimize  C_compile(G) + C_source_transform(R,X) + C_store(G,Z,E)
        + C_distribute(G,versions) + C_activate(A,G,Z,E)
        + C_verify(P,X,Xhat) + C_update + C_energy

subject to:
   Preserve(P, X, Xhat, task=T)         == SAT under independent verifier
   AllRequiredWitnesses(P)             == SAT
   Compatible(decoder, grammar, payload)== true
   latency <= device_limit; memory <= device_limit; energy <= device_limit
   no unreviewed omitted critical fields; no invented exact facts
```

A finite constraint solver can report `SAT` only for **its explicitly modeled constraints**, with `domain_admission=INCONCLUSIVE` until a trusted verifier. Use `UNSAT` for a proved modeled violation, `UNKNOWN` for missing information, indeterminate semantics or bounded search exhaustion. Do not claim `UNKNOWN` is `UNSAT`.

### Grammar lineages

**Existing v1.4 structural grammar:**

```ebnf
Relation<A,B> = EDGE<P:A→B>
              | PATH(Relation<A,M>, Relation<M,B>)
              | AND(Relation<A,B>, Relation<A,B>);
```

**Proposed activation grammar; only declarations are present in PR #69:**

```ebnf
ActivationPlan = RegimeDefinition+ Operator* ConstraintSet;
Operator       = PRESERVE(field_set)
               | TRANSITION(from_regime, to_regime, reviewed_mapping)
               | ACTIVATE(decoder_version, module_set, payload_ref)
               | VERIFY(obligation_set, witness_refs)
               | FALLBACK(baseline_regime);
```

**Explicit separation:** grammar typing and graph equivalence do **not** establish clinically correct translations or pixel/video identity.

## 3. Architecture and workstream order

```text
Original sources + custody
   -> reviewed PackSpec / typed ConstraintIR / purpose contract
   -> bounded candidate regime generator (RCT)
   -> finite constraint evaluation + counterexamples
   -> typed semantic AST / reusable grammar / versioned codebook
   -> source-preserving encoder + residual + compatibility manifest
   -> distributed artifact (model/grammar updates + title payloads)
   -> sandboxed local activation + reverse mapping / fallback
   -> independent fidelity and PackSpec verifier + evidence receipts
   -> research ledger + Semantic Gardener + bounded multi-agent experiments
   -> reviewed promotion -> signed immutable decoder version
```

**Milestones:** M0 foundation and evidence guardrails; M1 executable semantic transitions; M2 compiled activation and cost accounting; M3 real media prototype; M4 independent evaluation and agent research; M5 limited supported-device pilot. Product launch is **conditional on measured results**; no deadline or expected compression ratio is assumed.

**Priority:** P0 correctness/fail-closed prerequisites; P1 reproducible research and working prototype; P2 optional scaling, autonomy and commercial readiness. **Story IDs are stable** and may become GitHub Issues; no checkbox should be marked complete from synthetic success alone.

## 4. User stories and acceptance criteria

### EPIC E01 — Research specification, reproducibility and baseline inventory

**US-001 · P0 · Source and capability inventory**  
As a researcher, I want each claimed implementation linked to exact source and evidence so reviewers can distinguish proposals from working code.  
**Acceptance:** (1) Machine-readable `capabilities.json` lists module, branch/commit, status, test and known limitations. (2) PR #69 remains IN_REVIEW until merged. (3) CI rejects a DONE claim with no link to passing test receipt. (4) Report explicitly lists unavailable video decoder and independent admission.

**US-002 · P0 · Versioned schema catalog**  
As an SDK developer, I need schemas for grammar, source, PackSpec, transform, payload, receipt and verdict.  
**Acceptance:** (1) JSON Schema and example fixtures for each envelope. (2) Schema identifiers include major/minor version. (3) Unknown operator, duplicate ID, invalid type, oversize payload and incompatible major version fail deterministically. (4) Round-trip serialization is deterministic.

**US-003 · P0 · Independently replayable research harness**  
As a reviewer, I want one command to reproduce a finite source-to-receipt experiment.  
**Acceptance:** (1) Pinned tool/runtime versions and fixed fixtures. (2) Command emits source/policy/grammar digests, exact arguments, stdout and machine-readable result. (3) Repeat yields identical structural verdicts. (4) Any unavailable dependency causes explicit SKIP/UNKNOWN, not synthetic PASS.

**US-004 · P1 · Risk, prior art and novelty register**  
As a scientific reviewer, I want clear novelty boundaries against AV1, learned codecs, knowledge compilation, truth-maintenance, GraphRAG and generative video.  
**Acceptance:** (1) Each claimed novelty links to a falsifiable comparator. (2) Prior-art citations have dates/versions. (3) No generic “first” or “better compression” claim without experiment. (4) Negative results are retained.

### EPIC E02 — PackSpec as an executable preservation contract

**US-005 · P0 · Purpose-scoped information obligations**  
As a policy author, I want to declare which source distinctions are indispensable for a given task.  
**Acceptance:** (1) Schema expresses mandatory fields, exact fields, allowable approximation and unanswered/unknown distinctions. (2) Every required field maps to immutable source anchors. (3) Unspecified critical fields cannot silently be treated as disposable. (4) Contract identifies task, author, reviewer, version and authorization scope.

**US-006 · P0 · ConstraintIR-to-activation binding**  
As a governance engineer, I want a reviewed mapping from actual PackSpec ConstraintIR to activation obligations.  
**Acceptance:** (1) Use existing `tools/packspec_compiler` and `unified_gate.py`; do not create a second self-certifying admission engine. (2) Each mapped obligation references reviewed IR node IDs, source hash, omission permission and independent-review signature. (3) Deferred/unsupported semantics remain UNKNOWN. (4) Any mismatch REFUSEs use.

**US-007 · P0 · WitnessGraph and evidence independence**  
As an auditor, I want to prevent multiple derived copies of one source from counting as independent proof.  
**Acceptance:** (1) Witness derivation graph records source roots and custody. (2) Shared roots collapse under independence calculation. (3) Contradictory, stale or missing witnesses cannot satisfy exact-information preservation. (4) Canonical APX WitnessGraph behavior is used or tested against golden fixtures; discrepancies fail closed.

**US-008 · P0 · Omission and residual audit**  
As a PackSpec reviewer, I want to know exactly what a regime discards or must reconstruct.  
**Acceptance:** (1) Each candidate emits preserved, approximated, omitted, unknown and residual-required fields. (2) Every omission references a governing obligation and review disposition. (3) Unauthorized omissions block activation. (4) Replaying against a changed PackSpec invalidates stale approvals.

**US-009 · P1 · Domain preservation profiles**  
As a domain owner, I want separate profiles for education, clinical-description translation, legal contracts and video fidelity.  
**Acceptance:** (1) At least four source-anchored PackSpec fixtures, not one universal policy. (2) Clinical case distinguishes symptoms from diagnosis; legal case protects role bindings; video case protects text/timing. (3) Independent reviewers score adversarial examples. (4) Failing examples remain visible.

### EPIC E03 — RCT decision and regime-transition engine

**US-010 · P0 · RCT typed grammar integration**  
As a grammar researcher, I want the existing `EDGE/PATH/AND` compiler to be callable by the new candidate pipeline.  
**Acceptance:** (1) Reuse the existing module rather than rewriting it. (2) Typed endpoints checked on `PATH`; shared endpoint types checked on `AND`. (3) Unique minimal candidate requirement and budget-driven UNKNOWN retained. (4) Source fact IDs retained through path derivation.

**US-011 · P0 · SAT/UNSAT/UNKNOWN semantics**  
As an evaluator, I want explicit distinction between modeled feasibility and domain validity.  
**Acceptance:** (1) SAT only if every modeled obligation is satisfied. (2) UNSAT includes minimal available counterexample and violated clause. (3) Missing data or exhausted search returns UNKNOWN. (4) Finite SAT never emits QualityRag ADMIT or can_generate=true by itself.

**US-012 · P0 · Purpose-preserving regime transition**  
As a developer, I want a `TRANSITION` operator that actually transforms a finite typed structure.  
**Acceptance:** (1) Executes at least one source-anchored reversible mapping on non-video data. (2) Produces a transform trace and versioned source hash. (3) Unknown role/negation/temporal cases refuse or preserve raw source. (4) Round-trip tested for required distinction equivalence; no invented labels.

**US-013 · P1 · RCT candidate search with early stopping**  
As a cost engineer, I want bounded regime search so the system does not exhaust resources exploring unlikely options.  
**Acceptance:** (1) Explicit candidate count, depth, wall-clock/CPU and memory limits. (2) Deterministic selection for fixed search inputs. (3) Inconclusive search reports budget and discarded candidates. (4) Baseline “stay in present regime” is always considered.

**US-014 · P1 · Constraint compilation and reusable decisions**  
As a grammar engineer, I want recurring solved subproblems compiled into reusable operators.  
**Acceptance:** (1) Compilation records input obligation fingerprints and compiler version. (2) Repeated equivalent queries reuse artifacts without changing verdicts. (3) Invalidated input/policy triggers recompile. (4) Actual compiled artifact bytes, construction time, cache hits and runtime costs measured.

**US-015 · P1 · Finite equivalence proof and counterexamples**  
As a researcher, I want exhaustive checks on bounded input domains before trusting a transformation.  
**Acceptance:** (1) Compare relevant query results across source and transformed graph for all finite test pairs. (2) Include negative witnesses and role/order reversals. (3) Failure emits reproducible counterexample. (4) Result is scoped to finite graph and never generalized as universal meaning conservation.

### EPIC E04 — Semantic Codex grammar, source adapters and residuals

**US-016 · P0 · Typed semantic intermediate representation**  
As an encoder developer, I want one canonical AST for source observations and transformation dependencies.  
**Acceptance:** (1) Typed entities, roles, polarity, quantity/unit, temporal order, modality, provenance and unknowns are representable. (2) Invalid joins/roles rejected by type checker. (3) Source quote, byte/character anchors and hashes stored. (4) Canonical serialization round-trips.

**US-017 · P0 · Exact information and reversible source custody**  
As an auditor, I need access to everything the semantic representation omitted.  
**Acceptance:** (1) Raw-source immutable reference or lossless original bytes retained. (2) Every omission has a location and residual/refetch plan. (3) Content hash verification catches corruption. (4) Unavailable original causes an explicit fidelity limitation/REFUSE.

**US-018 · P1 · Source adapters (text, PDF, HTML, CSV/SQL)**  
As a user, I want to ingest familiar documents without losing citation boundaries.  
**Acceptance:** (1) Two complete initial adapters (e.g., PDF and CSV), plus text fixture. (2) Text/tabular spans map back to original pages/rows. (3) Unsupported structure is marked UNKNOWN, not silently dropped. (4) Unit/regression tests include duplicated headings and malformed input.

**US-019 · P1 · Review-gated relation and role extraction**  
As a semantic reviewer, I need extraction candidates with precise provenance.  
**Acceptance:** (1) Reuse existing v1.2 explicit `RELATE` and v1.3 bounded linguistic extractors. (2) Opposite polarity candidates quarantined. (3) Caller endorsement remains unauthenticated until authorization added. (4) Tests include actor/beneficiary swaps and negation changes.

**US-020 · P1 · Reusable grammar registry and dependency DAG**  
As a decoder developer, I want grammar components addressed by stable content hash and dependent versions.  
**Acceptance:** (1) DAG is acyclic and dependencies are typed. (2) Resolution identifies missing/incompatible modules before use. (3) Signed release metadata covers transitive dependencies. (4) Authorized rollback to a signed, compatible, non-revoked release is tested; minimum-version policy remains enforced.

**US-021 · P2 · FF-RCT native-regime integration**  
As an APX researcher, I want FF-RCT reconstruction to use authentic canonical semantics, not a renamed reference-frame prototype.  
**Acceptance:** (1) Original APX native interfaces integrated through authorized adapters. (2) Cross-repo golden cases and negative cases pass. (3) Reference prototype remains explicitly labeled until parity proven. (4) Compression and reconstruction cost evidence attached independently.

### EPIC E05 — Activation language and local execution

**US-022 · P0 · Activation grammar v0.1 baseline**  
As a grammar author, I want bounded `PRESERVE/TRANSITION/ACTIVATE/VERIFY/FALLBACK` declarations and finite budget checks.  
**Acceptance:** (1) PR #69 merged after required CI and review. IN_REVIEW or a blocking failure never satisfies completion. (2) Synthetic clinical/video fixtures and deterministic tests pass. (3) Unsupported operators rejected. (4) The baseline returns `INCONCLUSIVE` and `can_generate=false` without independent review. **Current status: IN_REVIEW**.

**US-023 · P0 · Executable finite ACTIVATE/VERIFY/FALLBACK**  
As a client developer, I want operators that can execute a constrained transformation and verify declared requirements.  
**Acceptance:** (1) Typed interpreter implements bounded, sandboxed operators with no `eval`/dynamic imports. (2) Uses actual transformed output, not merely stated `preserves` lists. (3) VERIFY compares actual output to all anchored obligations; fallback must independently satisfy authorization, compatibility, preservation and resource limits. At most one fallback attempt; failure terminates in REFUSE without releasing output. (4) Replay emits deterministic execution trace.

**US-024 · P0 · Model and grammar compatibility manifest**  
As a streaming client, I want exact dependency and version checks before playback.  
**Acceptance:** (1) Manifest pins payload codec, grammar hash, model hash, runtime ABI and required modules. (2) Missing, incompatible or unsigned module refuses/fallbacks. (3) Old payloads are decoded only by verified-compatible decoders. (4) Incompatible upgrade cannot silently alter old content.

**US-025 · P1 · Sparse activation and resource controls**  
As a viewer, I want a local engine that activates only needed modules within my device limits.  
**Acceptance:** (1) Module selection emits rationale and module list. (2) CPU/GPU, RAM, latency and energy/cold-start measured. (3) No exceeding declared hard budgets without explicit error/fallback. (4) Compare sparse vs full activation at equivalent fidelity.

**US-026 · P1 · Deterministic finite reconstruction**  
As an evaluator, I need an exact reconstruction baseline before using probabilistic generation.  
**Acceptance:** (1) Structured/text source can be reconstructed byte-for-byte or with clearly specified canonical normalization. (2) Residual-only errors cause REFUSE. (3) Fixed inputs/versions produce identical outputs and hashes. (4) Tests cover missing, modified and out-of-order segments.

**US-027 · P2 · Device module updates and rollback**  
As a device owner, I want grammar capabilities updated independently from content downloads.  
**Acceptance:** (1) Atomic signed module update, version pinning and checksum verification. (2) Interrupted download resumes or reverts safely. (3) A/B old/new runtime reconstructs pinned golden content identically for exact obligations. (4) Bandwidth, cache residency and update cost recorded.

### EPIC E06 — Real video codec research vertical slice

**US-028 · P1 · Real audiovisual dataset and licensing**  
As a researcher, I want authorized, representative clips with exact ground truth.  
**Acceptance:** (1) At least 100 licensed/owned short clips representing repeated and diverse settings. (2) Separate training/development/held-out families with provenance and no leakage. (3) Audio, on-screen text, timing and scene dynamics annotated. (4) Dataset manifest reproducible and redistributability respected.

**US-029 · P1 · AV1 and learned-codec baselines**  
As a codec researcher, I need fair comparison with contemporary standards.  
**Acceptance:** (1) Encode/decode scripts for AV1 and one reproducible neural codec where licensing permits. (2) Same resolution, frame rate and fidelity obligations. (3) Include full model/download/storage/energy/compute costs. (4) Report bitrates, artifacts and statistical intervals; no cherry-picked clips.

**US-030 · P1 · Shared grammar video encoder prototype**  
As an encoder engineer, I want a real payload containing scene features, temporal information and residuals.  
**Acceptance:** (1) Ingest actual frames and output a versioned decodable payload. (2) Decoder manifest pins shared model and modules. (3) A complete decode demonstrably reconstructs playable clip. (4) Encoding time, bytes, model size and fallback ratio measured. **Not accomplished by PR #69**.

**US-031 · P1 · Frame/semantic/exact fidelity evaluation**  
As a rights holder, I need to know what the decoder changed.  
**Acceptance:** (1) Frame quality scored by reproducible metrics plus blinded human assessment. (2) Subtitle text, signs, sequences and specified identities checked independently. (3) Audio synchronization and missing-frame violations reported. (4) PackSpec failures block claims of quality equivalence.

**US-032 · P1 · Model amortization and catalog economics**  
As a streaming operator, I want total costs compared across different catalog sizes and viewing patterns.  
**Acceptance:** (1) Account for grammar construction, encoding, residuals, model installation, updates, bandwidth, storage, decoding electricity and verification. (2) Analyze cold/new viewer, frequent viewer, smart TV and mobile cases. (3) Break-even conditions plus uncertainty bounds presented. (4) If no crossover, report negative result.

**US-033 · P2 · Streaming segment delivery and seek**  
As a viewer, I want random access and adaptive playback without full title decoding.  
**Acceptance:** (1) Segment index supports seek, pause/resume and bitrate changes. (2) Scene state dependencies are explicit. (3) Missing module/segment falls back without silent frame corruption. (4) Measure startup latency, buffering and seek times against AV1 baseline.

### EPIC E07 — Semantic Gardener and cumulative conversation research

**US-034 · P1 · Append-only conversation tree**  
As a researcher, I want turns, concepts, hypotheses and branches with explicit provenance and forks.  
**Acceptance:** (1) Stores source turn ID/hash, actor and timestamp. (2) Branches can fork/rejoin without cycles. (3) Replay deterministically rebuilds tree after restart. (4) No inference-generated concept is treated as reviewer-approved.

**US-035 · P1 · Dialectical operations and reversible pruning**  
As a scientist, I want `PROPOSE/CHALLENGE/TEST/SYNTHESIZE/PRUNE/REOPEN` to preserve alternatives and failures.  
**Acceptance:** (1) All transitions are append-only events. (2) PRUNE deactivates rather than deletes. (3) SYNTHESIZE records dependencies but never inherits VALIDATED from parent. (4) REOPEN restores reference context and prior counterexamples.

**US-036 · P1 · Evidence-state separation and Research Ledger link**  
As an auditor, I want inquiry status separate from evidence status.  
**Acceptance:** (1) Maps hypotheses to `tools/research_ledger` claims. (2) No VALIDATED promotion without independent verifier and evidence IDs. (3) Dependency uncertainty propagates as unresolved. (4) Tamper and hash-chain tests detect corruption within stated trust boundary.

**US-037 · P2 · Gardener proposal loop and review UI**  
As a long-running project owner, I want periodic suggestions about duplicates, contradictions and high-value next experiments.  
**Acceptance:** (1) Bounded scheduled job operates only on authorized sources. (2) Produces candidate events with source anchors, confidence/calibration and suggested cost. (3) Structural edits are previewable and reversible, promotion requires review. (4) Reports false merges, branch churn, cost and utility; no autonomous truth claim.

### EPIC E08 — Multi-agent grammar evolution

**US-038 · P1 · Isolated agent experiment harness**  
As an orchestrator, I want parallel agents to propose candidates without editing trusted grammar directly.  
**Acceptance:** (1) Candidate agents run with scoped CPU/token/time and tool permissions. (2) Every proposal includes parent grammar hash, patches and rationale. (3) Restricted execution sandbox prevents arbitrary host changes. (4) Evaluation always runs on pinned code/datasets.

**US-039 · P1 · Dedicated agent roles**  
As a research lead, I want decomposition, grammar compiler, activation optimizer, PackSpec guardian, counterexample and FF-RCT economist agents.  
**Acceptance:** (1) Each has a distinct versioned contract/schema. (2) Roles produce inspectable artifacts, not opaque prose. (3) Guardian can block but cannot invent verification evidence. (4) Integration tests show disagreement and escalation, not forced consensus.

**US-040 · P1 · Adversarial evolution and held-out gates**  
As a reviewer, I want grammar improvements challenged on unseen cases.  
**Acceptance:** (1) Family-disjoint holdouts are hidden from proposing agents. (2) Test actor/recipient reversal, negation, time, units, captions, residual tamper and incompatible model. (3) Any critical regression blocks promotion. (4) False-accept rate and missed-counterexample rate tracked.

**US-041 · P1 · Co-evolving encoder/decoder candidates**  
As a codec researcher, I want joint proposals tested against fixed-encoder/fixed-decoder ablations.  
**Acceptance:** (1) Run three arms: fixed pair, decoder-only evolution, paired evolution. (2) Exactly the same held-out content and PackSpec fidelity contract. (3) Count all additional training/search compute. (4) No “compression advantage” claimed if paired arm does not outperform a qualified baseline within uncertainty.

**US-042 · P2 · Pareto promotion and resource scheduler**  
As a platform owner, I want agents to select experiments using RCT under finite budgets.  
**Acceptance:** (1) Rank by expected information/decision value against investigation cost. (2) Pareto frontier covers bytes, latency, energy, fidelity and total cost; reject dominated options unless justified. (3) Budget exhaustion stops runs predictably. (4) Promotion requires independent reviewer approval and signed immutable release.

### EPIC E09 — Security, privacy, interoperability and deployment

**US-043 · P0 · Tenant isolation and source authority**  
As an enterprise user, I want provenance and data access enforced for every transformation and query.  
**Acceptance:** (1) Authenticated principal and tenant-scoped authorization per source and artifact. (2) Cross-tenant reads, guessed IDs and leaked residuals denied in tests. (3) Reviewer and custodian identities cryptographically bound. (4) Logs do not disclose source content outside authorized scope.

**US-044 · P0 · Signed artifact and anti-replay pipeline**  
As a client, I want to reject tampered PackSpecs, grammar modules and evidence receipts.  
**Acceptance:** (1) Key rotation and version policy documented. (2) Signatures bind source, grammar, policy, model, decoder and relevant run IDs. (3) Unauthorized replay/downgrade attacks produce refusal; explicit authorized rollback must respect compatibility, revocation and minimum-version policy. (4) Existing signed-bundle code reused, not silently substituted with raw hashes.

**US-045 · P1 · SDK and CLI parity**  
As an integrator, I want the runtime through Python and at least one of Java/TypeScript, consistent with QualityRag SDK practices.  
**Acceptance:** (1) JSON/typed interfaces support validation, evaluate, trace and fallback. (2) Golden fixtures produce identical finite verdicts across languages. (3) Unsupported API options explicitly fail. (4) Examples demonstrate external PackSpec and source-backed receipts.

**US-046 · P2 · Offline mobile/TV feasibility pilot**  
As a viewer, I need playback within real device limitations.  
**Acceptance:** (1) Two different device classes benchmarked with pinned versions. (2) Startup, memory, sustained throughput, thermal throttling, update traffic and power measured. (3) Failed or unsupported decoder triggers conventional baseline playback. (4) No production release until security, licensing and fidelity review.

### EPIC E10 — Peer-review evaluation, evidence and delivery

**US-047 · P0 · Independent acceptance ledger**  
As a reviewer, I want every result categorized as implementation, synthetic test, measured experiment or independently validated claim.  
**Acceptance:** (1) Evidence links to commits, CI runs, original source fingerprints, dataset splits and signed reviewers. (2) Missing evidence stays UNVERIFIED/INCONCLUSIVE. (3) A test result does not imply product performance. (4) Negative findings and uncertainty preserved.

**US-048 · P1 · Pre-registered controlled experiments**  
As a researcher, I want hypotheses and rejection conditions fixed before evaluating the final holdout.  
**Acceptance:** (1) H1 storage bytes, H2 total cost, H3 activation speed, H4 preserved distinctions, H5 Gardener research continuity and H6 agent evolution benefit each have stated independent/dependent variables. (2) Compare AV1, learned codec, no-grammar ablation, fixed grammar, evolving grammar. (3) Define sample size rationale, paired statistical methods and confidence intervals before testing. (4) Raw scripts and failure cases reproducible.

**US-049 · P1 · Four worked real-world demonstrations**  
As a reviewer, I want complete input → PackSpec → grammar → transform → activation → witness → verdict examples, not decorative diagrams.  
**Acceptance:** (1) Child-to-clinician: preserves symptoms while blocking unsupported diagnosis. (2) Nursing instruction: NOT/EXCEPT and units cannot disappear. (3) Contract: role reversal/negation test REFUSEs. (4) Actual short video: subtitle, frame/timing and residual tests; synthetic-only examples clearly labeled until real input works.

**US-050 · P1 · Peer-review package and reproducible figures**  
As a scientist, I want a paper backed by executable artifacts.  
**Acceptance:** (1) Paper includes exact existing grammar syntax, genuine PackSpec excerpts, versioned experimental proposals, and limitations. (2) All figures regenerated by committed scripts from receipts. (3) Repository and PDFs contain a traceability matrix from each research claim to an experiment. (4) No “validated compression improvement” in abstract until independently established.

**US-051 · P2 · Release readiness and pilot stop conditions**  
As a deployment owner, I want a release gate with rollback and measurable discontinuation criteria.  
**Acceptance:** (1) Complete security/privacy review, supported-device contracts, signed artifacts and error telemetry. (2) Hard thresholds for fidelity and no silent critical-field loss. (3) Pilot compared to conventional codec for realistic network and client costs. (4) Publish failure or no-crossover results; release not automatic.

## 5. Dependency path and recommended execution batches

| Batch | Order | Stories | Exit gate |
|---|---|---|---|
| **A — Governance and spec** | First | 001,002,003,004,005,006,007,008,011,022,024,043,044,047,048a | Versioned schema, enforceable custody and fail-closed finite verdicts; PR #69 merged only after CI |
| **B — Real semantic executable slice** | After A | 009,010,012,015,016,017,018a,019,023,026 | Reviewed source → typed AST → reversible transition → residual → verified finite obligations |
| **C — RCT + economics** | After B | 013,014,020,025,032a | Compile/reuse cost measured; stay-vs-transition decision justified on capability-matched workloads |
| **D — Media proof-of-concept** | After B/C | 028,029,030,031,032b,033 | Actual decodable video, exact-field guardrails and matched AV1 comparison |
| **E — Research memory + agents** | After evidence baseline | 034,035,036,038,039,040,041,042 | Agent improvements evaluated on hidden holdouts with immutable provenance and promotion gate |
| **F — Production feasibility** | Conditional | 018b,021,027,037,045,046,048b,049,050,051 | Independently reviewed reproducibility, real-device results, signed release and rollback |

Dependencies are **logical, not permission to postpone all tests**: write failing acceptance tests and synthetic counterexamples early. Batch B may be developed in parallel with controlled baseline setup in Batch D; promotion remains gated.

## 6. Definition of Done — applies to every story

- Code, API schemas, docs and a runnable example are committed to a review branch and merged only after the configured required CI checks pass.
- Acceptance criteria have direct tests or audited evidence; tests include negative, missing-data and tampering cases.
- Reviewer can replay from authorized, immutable original artifacts and obtain a stable receipt.
- Genuine measurements are labeled **OBSERVED**; invented estimates are **ASSUMED**; missing costs remain **UNKNOWN**.
- No semantic admission from source fingerprints, agent consensus or finite synthetic SAT alone.
- Security and access control are included wherever sources, personal data, models or agents cross boundaries.
- Failure modes have explicit action: REFUSE, UNKNOWN, FALLBACK or REQUIRES_REVIEW.
- Progress table records implementation status and exact PR/commit/experiment links; no user-story counting by intent alone.

## 7. Experiment protocol and success/failure matrix

| Experiment | Controls and comparison | Success evidence | Failure / negative result |
|---|---|---|---|
| Clinical regime transition | Source symptoms + clinician profile; exact-observation contract | Symptoms/context preserved, no unsupported diagnosis; source anchors reconstructable | Adds diagnosis, deletes timing or treats unknown as absent |
| Nursing instruction | Same original negation/unit/dose in raw and semantic representations | NOT/EXCEPT, unit and actor survive; verified deterministic query equality | Negation/unit loss or fabricated clinical advice |
| Legal roles | Same parties, reversed roles/negation adversary | Typed role inventory detects inversion and refuses | Equivalent lexical tokens falsely pass |
| Video shared model | Equal-quality AV1, learned codec, fixed and evolving Semantic Codex | Real decoded files, quantified byte/energy/cost advantage on held-out corpus with exact fields preserved | Better file size but worse total cost or altered required text/timing |
| Grammar compilation | No compiled cache vs compiled reusable constraint artifact | Measured break-even under repeated equivalent workloads | Compile overhead never amortized or cached verdict diverges |
| Semantic Gardener | Transcript baseline vs graph baseline vs event-sourced Gardener | Higher independently scored continuity and lower false merges at stated cost | New branches increase but recovery/accuracy does not |
| Multi-agent evolution | Fixed grammar vs decoder-only vs co-evolution | Held-out improvements including search/agent spend and independent review | Benchmark leakage, unverifiable improvements, unbounded compute |

### Statistical and economic obligations

- Split by underlying scene/problem family, not just renamed labels.
- Report sampling plan, confidence intervals, effect sizes and invalid/abstained rates.
- Include per-device update/model bytes and normalized cost per watched hour; count model distribution across new users and cache evictions.
- Report compression, startup latency, seek time, decode energy and exact-field failure rate separately; no single blended score hides violations.
- Define experimental rejection thresholds before opening the final holdout. **No target savings number is fabricated by this plan.**

## 8. Test and implementation commands (existing anchors)

```bash
# Existing Semantic Store / RCT suite
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v

# Existing PackSpec compiler
python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py' -v

# Existing research ledger
python -m unittest discover -s tools/research_ledger/tests -p 'test_*.py' -v

# Experimental full RCT demonstration
python tools/semantic_store/rct_demo.py

# PR #69 only, when checked out:
python -m unittest discover -s tools/semantic_store/tests -p 'test_activation_constraints.py' -v
```

See `docs/RCT-END-TO-END-RESEARCH-DELIVERY.md`, `docs/RCT-TYPED-GRAMMAR-v1.4.md`, `docs/RCT-PACKSPEC-GOVERNANCE-BRIDGE-v1.6.md`, and `tools/packspec_compiler/TYPED-IR.md` for exact current limitations. A successful test in those modules is *not* verification of the proposed video codec.

## 9. Open research questions and hard stop rules

1. **Grammar compactness:** Under which workload families can compiled constraint representations avoid exponential growth?
2. **Task-relative isomorphism:** Which queries must be preserved when moving from child language to clinician terminology or pixels to semantic scene states?
3. **Decoder risk:** How can generative components remain useful without hallucinating exact details? Where must a residual or native-coded fallback always win?
4. **Activation economics:** When do cold-start, GPU/energy, device compatibility and update costs overwhelm smaller per-title payloads?
5. **Research agents:** Do agents find useful new operator structures, or simply optimize a fixed predefined search space and overfit synthetic fixtures?
6. **Source authenticity:** Can evidence be independently verified rather than merely hashed, signed by a caller or voted on by agents?
7. **Permission and licensing:** Can the benchmark media/models be legally used and results redistributed?
8. **Deployment:** A scientifically inconclusive result must remain inconclusive even when all software CI checks are green.

**Hard stop:** Do not advertise production-ready semantic preservation, superior compression, medical safety, independent formal proof or automatic model evolution until separately established by the appropriate experiments and external review.

---

## 10. Traceability: first concrete implementation

- [PR #69 — activation constraint runtime](https://github.com/cyrillesaxo/QualityRag/pull/69): bounded declared-regime evaluation; **NOT** video activation.
- Existing RCT typed grammar: `tools/semantic_store/rct_typed_grammar.py`.
- Existing governance: `tools/packspec_compiler/unified_gate.py`.
- Existing typed PackSpec: `tools/packspec_compiler/TYPED-IR.md`.
- Existing source and role extraction: `tools/semantic_store/rct_role_grammar.py`, `docs/SEMANTIC-CODEX-LINGUISTIC-RELATIONS-V1.3.md`.
- Existing research-memory persistence: `tools/research_ledger/ledger.py` and `postgres.py`.

**Backlog total: 51 numbered user stories across 10 epics.** Counts describe planned scope, not completed scope. Update this file whenever story status or evidence changes; preserve prior decisions in append-only research records.


## 11. Review amendments, execution dependencies and evidence (v0.2)

Stable parent story IDs US-001–US-051 remain unchanged. Suffixes below are
implementation tasks, not additional completed stories.

- **US-018a / Batch B:** one real UTF-8 structured-text adapter with exact byte custody,
  duplicate-key rejection, scalar type preservation and a replayable transform.
  **US-018b / Batch F:** remaining document adapters and page/row anchors.
- **US-032a / Batch C:** versioned lifecycle-cost model with explicit assumed/unknown
  inputs. **US-032b / Batch D:** populate measured encoder/decoder and baseline costs;
  predictions must not be reported as observed results.
- **US-048a / Batch A:** register hypotheses, metrics, thresholds, sample-size rationale,
  dataset-family split and blinded scoring rubric before holdout access.
  **US-048b / Batch F:** independently analyze registered experiments, report evaluator
  agreement, confidence intervals, abstentions, deviations and negative results.
- **US-024 precedes US-023, US-025 and US-030.** Prototype compatibility fingerprints
  do not satisfy signed production compatibility. Untrusted hashes never establish authority.
- **US-006/007/036/047 authority contract:** document trusted reviewer keys, role/scope,
  proposer/reviewer separation, expiry, revocation and binding to policy, data, output and
  run identity. Unauthorized, self-approved, expired or revoked receipts cannot authorize
  admission. Missing trusted verifier remains INCONCLUSIVE.
- **US-009/031/037/040/048 measurement contract:** pin metric versions, tolerances,
  rubric, evaluator-selection rules, agreement measure and rejection thresholds before
  final evaluation. Measurement alone is not a passing acceptance criterion.
- **US-016 semantic traceability task:** map canonical 12G, K/B/C/T, WitnessGraph,
  WBC and RCoC definitions to source specification/version, schema fields, operators,
  invariants and golden tests. Do not invent meanings for unavailable canonical concepts;
  missing source definitions block parity claims. US-021 canonical FF-RCT parity remains separate.
- **Gate order:** executable semantic slice → reusable activation and measured economics →
  real media evidence → Gardener/agent experiments → conditional supported-device pilot.
  Tests accompany each gate; no completion claim follows from implementing a subset.

### Implementation evidence — initial finite slice

| Stories | Implementation | Status / remaining boundary |
|---|---|---|
| US-012,018a,023,026 | tools/packspec_compiler/finite_activation.py | PARTIAL: real scalar JSON bijective field transform; pinned runtime/hash checks; actual reconstructed values compared to source; existing unified gate reused |
| US-003,011,017,024 | finite activation receipts and regression tests | PARTIAL: deterministic source/artifact/policy fingerprints and refusal tests; no signed authority, persistent custody service, general interpreter or complete manifest |
| All 51 parent stories | This backlog | No parent story marked DONE by this increment |

Reproduce the initial finite-slice checks:

~~~bash
python -m unittest discover -s tools/packspec_compiler -p 'test_finite_activation.py' -v
~~~

This research API returns candidate output only as research_output and never grants
can_generate. It accepts host-provided original bytes and a pinned artifact fingerprint;
it does not authenticate caller custody, policy completeness or semantic truth.
Fallback supplies an unreleased source reference and terminates; it does not execute
unverified code or release a failed reconstruction. Real RCT candidate selection,
signed compatibility and independent admission remain subsequent integration tasks.
