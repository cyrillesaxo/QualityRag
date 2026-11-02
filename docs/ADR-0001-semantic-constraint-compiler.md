# QualityRag — Semantic Constraint Compiler (Architecture ADR-0001)

Status: PROPOSED · 2026-11-02

## Thesis

The stable contract is **WHAT must hold**; the changing implementation is **HOW the system obtains and checks evidence**. QualityRag should not become another general RAG framework. It is a source-neutral compiler and runtime for verifiable semantic obligations, decision gating, and cost-bounded recovery.

The initial SDK (v0.1) only evaluates declared source counts, timestamps, and contradictions. It does **not** implement this architecture yet.

## Core planes

1. **Contract plane:** Versioned PackSpec declares subject, actor, scope, governing definition, temporal horizon, relevant exceptions, constraints, authority, thresholds, and evidence obligations. Each must have an explicit unknown state.
2. **Grammar/compiler plane:** Parse and normalize source-specific representations into a typed intermediate representation (IR). The compiler emits a deterministic check plan, dependent witness requirements, and unresolved obligations. LLMs may propose candidates but cannot self-certify.
3. **Evidence plane:** WitnessGraph records provenance, original authority versus derived interpretation, identity and shared-origin dependency, contradiction, time validity, and scope. Retaining two copies of one source is not independent corroboration.
4. **Assurance plane:** G1–G12 semantic loci plus the D15 matrix (DW/DD/DS × depth/breadth/channel/frame/implicature), where relevant to the PackSpec. A missing required test is NOT a PASS.
5. **Recovery plane:** Wgap (unresolved semantic/evidence obligations), HCR next-probe selection, budget and allowed capabilities. A policy-selected probe may narrow INCONCLUSIVE; no unbounded auto-approval.
6. **Decision/receipt plane:** ADMIT, REFUSE, INCONCLUSIVE; versioned reason codes, minimum witness set W_min when proven, unresolved obligations, provenance-bound receipts, and dependency replay on change (TERM/RCOC).
7. **Execution optimization:** Deterministic-first routing (AI Call Eliminator). Before a model call, ask whether typed policy and evidence are sufficient. Count suppressed and escalated calls without mistaking lower cost for correctness.

## Intended compilation interfaces

Input:
```json
{
  "schema": "qualityrag.packspec/v1",
  "subject": "example-question",
  "requirements": [
    {"id": "eligibility", "predicate": "eligibility.current",
     "authority": "official-source",
     "time_horizon": "current",
     "scope": {"region": "declared"},
     "evidence": {"min_independent_origins": 2, "require_primary": true}}
  ]
}
```

Proposed compiler outputs: `ConstraintIR`, `EvidenceObligation[]`, `ProbePlan[]`, `DecisionPolicy`, `EvaluationReceipt`. These are planned interfaces, NOT current SDK capabilities.

## Cross-language boundary

- `qualityrag-core`: canonical versioned JSON schema and golden conformance vectors; no frontend authority.
- `qualityrag-java`: Spring Boot filters/interceptors and native Java policy evaluator.
- `qualityrag-python`: FastAPI and LangChain/LlamaIndex retrieval hooks; metadata normalization and guarded answer generation.
- `@qualityrag/sdk`: TypeScript client / React UI for receipts and missing evidence. The browser does not become the authoritative enforcement point.
- Adapter layer: source-neutral; no forced vector database or LLM provider.
- Avoid hidden network calls in the deterministic evaluator.

## Phased extraction and acceptance criteria

### P0 — Semantic contract and invariants
- [ ] Add PackSpec v1 grammar, canonical normalization, strict versioning, schema validation, and golden fixtures.
- [ ] Tests reject malformed, unknown, contradictory, unsupported, and cross-scope inputs consistently in Java, Python and TypeScript.
- [ ] Preserve three-way decision semantics; no unsupported default ADMIT.

### P1 — WitnessGraph and triangulation
- [ ] Track source, origin, claim, derivation, scope, timestamp, authority, consent/classification.
- [ ] Shared-origin documents never count as independent evidence; contradictory authoritative witnesses block or require resolution.
- [ ] Compare prior, artifact and probe evidence; retain conflict and epistemic residue.

### P2 — Semantic gate
- [ ] Port canonical G1–G12 with explicit definitions and D15 deception census using source-derived golden tests.
- [ ] Required tests omitted => incomplete; explicit failure => refusal.
- [ ] Bound claims to tested scope, never globalize narrow evidence.

### P3 — Active recovery and efficiency
- [ ] Compute Wgap from requirements not licensed by evidence.
- [ ] Choose HCR next probe by expected utility, allowed authority, maximum cost, and request scope.
- [ ] Deterministic-first execution measures model calls avoided, false admissions, erroneous refusals and cost; comparisons retain safety parity.

### P4 — Public adoption
- [ ] Spring Boot starter; Python FastAPI/LangChain adapter; React receipt inspector.
- [ ] One reproducible naive-RAG-vs-QualityRag case with real provenance, adversarial tests and bounded claims.
- [ ] Publish reproducible benchmarks and honest limitations before marketplace package claims.

## Non-claims

This repository does not certify source truth, independent provenance, regulator acceptance, protected data compliance or general semantic correctness. The initial v0.1 project is a metadata gate, not a complete APX port. No raw private APX implementation, private data, credentials, or customer artifacts should be exposed.

## APX origin inventory

Private APX references: `packages/apx-pack-spec`, `packages/apx-evidence`, `packages/apx-assurance`, `packages/apx-regime`, `packages/apx-wbc`, `packages/apx-hcr`, `packages/apx-term`, `packages/apx-rcoc`, `packages/apx-receipts`. Extraction must be behaviorally validated with golden conformance tests; names alone do not imply equivalence.
