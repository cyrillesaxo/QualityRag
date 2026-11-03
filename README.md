# QualityRag

**Evidence completeness and semantic governance for retrieval-augmented generation.**

QualityRag evaluates a versioned **PackSpec** against retrieved evidence **before** an answer is produced. The SDK uses the same portable contract in Python, Java, and TypeScript/React.

**Status:** Experimental v0.1. Local, deterministic policy evaluator; not a proof of source authenticity, truth, regulatory compliance, or production readiness. No LLM is required for evaluation.

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

## APX PackSpec-derived examples in ten languages

The [APX example collection](examples/apx-packspecs/README.md) provides twelve verified metadata-gate scenarios based on SEMLOAN, Question Fan, FFI and software-selling PackSpecs, with corresponding examples for Java, Python, TypeScript, Go, C#, Rust, Kotlin, PHP, Ruby and Swift. They **project** the original semantic contracts into the experimental v0.1 evidence format; the SDKs do not execute the full originals.
