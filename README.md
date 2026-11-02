# QualityRag

**Evidence completeness and semantic governance for retrieval-augmented generation.**

QualityRag evaluates a versioned **PackSpec** against retrieved evidence **before** an answer is produced. The SDK uses the same portable contract in Python, Java, and TypeScript/React.

**Status:** Experimental v0.1. Local, deterministic policy evaluator; not a proof of source authenticity, truth, regulatory compliance, or production readiness. No LLM is required for evaluation.

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

## License

Apache-2.0. See `LICENSE`.
