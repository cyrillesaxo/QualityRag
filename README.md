# QualityRag

**Evidence-governed RAG and a growing Semantic Garden for grammar and activation research through RCT.**

QualityRag evaluates a versioned **PackSpec** against retrieved evidence **before** an answer is produced. The SDK uses the same portable contract in Python, Java, and TypeScript/React.

**Status:** Experimental v0.1. Local, deterministic policy evaluator; not a proof of source authenticity, truth, regulatory compliance, or production readiness. No LLM is required for evaluation.

## Watch QualityRAG in action

The fastest way to understand QualityRAG is to watch an evidence check fail safely, then see what additional evidence changes.

| 51-second overview | The Evidence Engine — 2 min 12 sec |
| --- | --- |
| [![Watch the QualityRAG overview: a missing condition changes the evidence decision](docs/training/homepage-45s/poster.jpg)](docs/training/homepage-45s/qualityrag-homepage-45s.mp4) | [![Watch The Evidence Engine: PackSpec, deceptive witnesses, verdicts, and the experimental Semantic Garden](docs/training/film-01-evidence-engine/poster.jpg)](docs/training/film-01-evidence-engine/qualityrag-the-evidence-engine.mp4) |
| **[Watch the short overview](docs/training/homepage-45s/qualityrag-homepage-45s.mp4)** · [Captions (VTT)](docs/training/homepage-45s/qualityrag-homepage-45s.vtt) | **[Watch the full narrated film](docs/training/film-01-evidence-engine/qualityrag-the-evidence-engine.mp4)** · [Captions (VTT)](docs/training/film-01-evidence-engine/qualityrag-the-evidence-engine.vtt) |

**Learn by doing:** [Getting started (3-minute video)](docs/training/episode-01-getting-started/episode-01-getting-started.mp4) · [QualityRAG Academy — 11 video-and-lab chapters](docs/academy/README.md) · [Complete training video catalog](docs/training/README.md).

*Click a thumbnail to open its narrated MP4. GitHub README pages show the poster links, not an arbitrary embedded HTML video player. The videos illustrate the current evidence gate and distinguish experimental research concepts from validated SDK behavior.*

## See the difference

| Traditional RAG | QualityRAG |
| --- | --- |
| ![Traditional RAG: chunk, embed, retrieve, assemble a prompt and generate an answer](docs/assets/traditional-rag.gif) | ![QualityRAG: source structuring, evidence governance and the Semantic Garden research loop](docs/assets/qualityrag-architecture.gif) |
| Retrieves relevant passages and generates an answer from the selected context. | Evaluates the PackSpec's declared evidence requirements before admitting an answer; missing or conflicting evidence can prevent admission. |

The traditional RAG animation depicts a representative baseline **without an explicit completeness contract**; RAG implementations can add their own guardrails. The QualityRAG animation illustrates the broader architecture, including the Semantic Garden's intended continuous grammar and activation research loop. It is not evidence that the full autonomous loop, semantic accuracy or compression superiority has been validated. Admission concerns declared requirements and supplied evidence metadata, not a guarantee of truth.

## Semantic Garden: a continuous RCT research loop

The central research deliverable is an agent-driven system that repeatedly finds, tests and retains better representation regimes while preserving the meaning required by the same PackSpec. **Grammar and activation evolve together.** A fixed codec, deterministic proposal roles or a predefined palette search alone do not fulfill this goal.

1. **Find failure:** identify lost distinctions, excessive representation or activation costs, and cases that perform worse than AV1.
2. **Investigate the regime:** record the constraints, representation choices and counterexamples that explain the failure.
3. **Propose changes:** agents revise grammar rules, reusable structures, residual strategies, activation dependencies and paired encoder/decoder behavior.
4. **Run controlled experiments:** compare each candidate with the current champion and AV1 on held-out families under the same PackSpec. Record setup, representation, activation and research costs; leave unmeasured costs explicit.
5. **Retain knowledge:** keep hypotheses, lineage, counterexamples, negative experiments and the conditions under which each result holds. The research tree keeps growing.
6. **Promote or reopen:** retain qualified, versioned research champions and reopen failed or dormant branches when new evidence warrants investigation.

Activation includes what is reconstructed, which modules load, their order and their resource constraints. **AV1 is the baseline and fallback, not the endpoint.** Untouched AV1 fallback can preserve its byte-size floor; it does not establish an advantage in latency, energy, total research cost or semantic compression.

### Executable implementation and current limits

The [continuous research engine](docs/CONTINUOUS-RCT-GARDEN.md) connects persistent Garden branches and the Research Ledger to a host-configured open-model proposer, bounded encoding/activation experiments, fresh evaluation cohorts and research-champion history. Its first backend learns source-bound literal productions and composes reversible operators with eager or on-demand chunk activation. Exact source reconstruction is checked, and unknown decoder installation cost forces original-source fallback.

```bash
python -m tools.activation_runtime.evolution \
  --garden /absolute/workspace/gardens/research/events.sqlite \
  --config /absolute/research-config.json \
  --model YOUR_INSTALLED_OPEN_MODEL --continuous --work-limit 200
```

Use the guide's explicit source-family splits and objective configuration. The worker runs until stopped, a budget is exhausted or a provider fails; without fresh evaluation families, it can continue development but cannot promote a research champion.

**Acceptance boundary:** this implementation is a first reversible research backend. It does not yet demonstrate the full autonomous semantic improvement loop, a mature video grammar or superiority over AV1. Scripted lifecycle tests and a provider protocol fixture do not substitute for a live model experiment. Earlier “software-complete” story counts describe component evidence, not fulfillment of that system-level goal. Research promotion grants neither semantic admission nor production release.

## How QualityRAG works (animated)

![Animated QualityRAG walkthrough showing question retrieval, PackSpec obligations, duplicate-origin evidence, INCONCLUSIVE abstention, new independent evidence, ADMIT, and a source-linked answer. The final frame labels Semantic Garden research as experimental.](docs/assets/qualityrag-how-it-works.gif)

**The key difference from ordinary RAG:** documents retrieved from the same origin do not automatically count as independent corroboration. QualityRAG checks the **versioned PackSpec** against the supplied evidence metadata *before* the application decides whether to generate an answer. Insufficient evidence results in **INCONCLUSIVE**, not an invented confident answer. **ADMIT** means the supplied inputs pass the declared checks; it does **not** prove that their sources are truthful.

The final animation frame shows the **separate, experimental Semantic Garden** research loop for grammar and activation ideas. This is not a capability of the stable evidence-gate SDK, and research results are not promoted automatically.

[Read the walkthrough and regenerate the GIF](docs/README-ANIMATION.md)


## PackSpec configuration choices

Keep your policy **inside the application**, supply it as a **JSON property or mounted file**, or manage versions centrally through **QualityRag Studio**. All approaches use the same evidence evaluator; the Java SDK includes an explicit, fail-closed source selector.

**[PackSpec source configuration guide](docs/PACKSPEC-SOURCES.md)** (Java, Python, TypeScript) · **[Studio registry](docs/STUDIO-REGISTRY.md)**

## Decision semantics

- **ADMIT**: all declared requirements have valid supporting evidence under the supplied metadata.
- **REFUSE**: a requirement is contradicted or an explicit violation has been recorded.
- **INCONCLUSIVE**: evidence is absent, stale, source-dependent when independence is required, unverified, or lacks required coverage.

**ADMIT only means the supplied input satisfies the specified checks; it never proves the underlying source is truthful.** Integrators should refuse or ask for more evidence on either REFUSE or INCONCLUSIVE.

## Repository

- `contracts/qualityrag.schema.json` – portable PackSpec, witness, and evaluation contract
- `sdk/python` – zero-dependency Python engine and tests
- `sdk/java` – Java 17 Maven SDK with Jackson and JUnit
- `sdk/typescript` – TypeScript SDK and React hook
- `examples/` – shared input and expected result

## Try it

Then take the **[QualityRag Academy](docs/academy/README.md)**: eleven problem-driven chapters, each with a cinematic episode, a real lab, a war game and a quiz.

New here? Watch **[QualityRag 101, episode 1: Getting started](docs/training/README.md)**, a three-minute animated walkthrough of installing, signing in, and checking your first answer.


Python (from repository root):

```sh
PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests
PYTHONPATH=sdk/python python examples/python_demo.py
```

Java: `cd sdk/java && mvn test`

TypeScript: `cd sdk/typescript && npm install && npm test && npm run build`

## Source lineage and scope

Concepts adapted from private APX implementation as of 2026-11-02:

| Capability | APX reference | Public v0.1 |
| --- | --- | --- |
| Versioned policy | `packages/apx-pack-spec` | Simplified portable PackSpec |
| Evidence lineage | `packages/apx-evidence` | Origin key + source reference |
| Decision and refusal | `packages/apx-assurance` | Deterministic ADMIT/REFUSE/INCONCLUSIVE |
| Independent corroboration | `packages/apx-evidence` | Distinct origin count |
| D15 deception census | `packages/apx-evidence` | **Not yet ported** |
| HCR, RCOC, TERM, W_min, receipts | APX assurance stack | **Not yet ported** |

No private infrastructure, credentials, customer records, or private APX source tree is included. See `docs/ROADMAP.md` for parity criteria.

## Security

Only metadata and bounded evidence identifiers belong in receipts. Validate upstream source authority; do not count repeated copies as independent corroboration. Apply access control to documents before indexing/retrieval. Avoid logging retrieved content or sensitive data.

## Research lineage and references

**Cyrille Eloundou** — APX framework author and research reference for the PackSpec, semantic governance, constraint-verification, and provenance concepts that informed QualityRag.

**APX project:** [apx.guide](https://apx.guide/) · [QualityRag enterprise retrieval training](docs/TRAINING.md) · [Reproducible example](examples/enterprise-rag/README.md)

QualityRag adapts concepts from APX for evidence-completeness decisions in RAG. It is a separate, experimental implementation. The APX website describes its own research and product claims; those claims are not independent validation of QualityRag's effectiveness.

## License

Apache-2.0. See `LICENSE`.

## Learn why QualityRag exists

Start with the **[training guide: five RAG failure scenarios, the case for deterministic evidence gates, and a runnable lab](docs/TRAINING.md)**. It explains when QualityRag is useful, what its current SDKs guarantee, and where their limitations remain.

## Source PackSpec compiler (experimental)

The [source PackSpec compiler](tools/packspec_compiler/README.md) inspects original APX YAML, JSON and text-bearing PDF specifications, preserves source fingerprints and locations, and creates **review-required constraint inventories**. Only explicitly reviewer-mapped evidence-presence obligations can be projected into a v0.1 QualityRag policy. It does **not** implement the full APX semantic grammar or automatically approve claims.

## APX PackSpec-derived examples in ten languages

The [APX example collection](examples/apx-packspecs/README.md) provides twelve verified metadata-gate scenarios based on SEMLOAN, Question Fan, FFI and software-selling PackSpecs, with corresponding examples for Java, Python, TypeScript, Go, C#, Rust, Kotlin, PHP, Ruby and Swift. They **project** the original semantic contracts into the experimental v0.1 evidence format; the SDKs do not execute the full originals.

## Signed Studio policy promotion (experimental)

The [signed Studio promotion guide](apps/registry/SIGNED-PROMOTION.md) explains offline Ed25519 signing, trust-store configuration, staged → approved → published policy distribution and signed-only Python client verification. The registry stores **public keys only**, never governance private keys. Its shared bearer token and local file storage remain development-grade; production RBAC, attested evidence custody and multi-instance sequence coordination are not yet implemented.

## Registry identity and independent policy approval

[OIDC governance and scoped RBAC](apps/registry/OIDC-GOVERNANCE.md) introduces verified JWT identities, separate policy author/approver/publisher roles, three-person signed promotion, and a local SHA-256 audit chain. The file-backed registry is still a single-writer development service; database transactions, interactive Studio login and independent audit anchoring remain outstanding.

## Transactional signed-policy promotions

The [PostgreSQL signed-promotion ledger](apps/registry/POSTGRES-SIGNED-LEDGER.md) implements service/environment row locking and atomic promotion/audit transactions for multiple registry instances. It is an opt-in **signed-only** backend; unsigned legacy operations explicitly fail rather than using file storage. PostgreSQL provisioning, independent audit anchoring and production deployment remain outside this implementation.

## Operational signed-registry readiness

The [PostgreSQL deployment and recovery runbook](apps/registry/DEPLOYMENT-RUNBOOK.md) describes checksummed advisory-locked migration, fail-closed startup, liveness/readiness probes, and a non-root registry container. It does not provision production database, identity or signing credentials.

