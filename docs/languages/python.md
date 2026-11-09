# QualityRag for Python

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

> **SDK status:** Experimental · Source-built · Base evidence metadata gate available


## 1. Prerequisites & setup

Python 3.10+ and a cloned repository. No runtime dependencies for the base SDK. Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests
```

## 2. API reference

`from qualityrag import evaluate`; extended: `from qualityrag.compiler import compile_pack, evaluate_compiled`.

## 3. Example: incomplete retrieval from a large PDF corpus

An enterprise RAG search returns page 74 of the **Payments Operations Handbook**, which describes recovery after a dependency timeout. It does **not** return page 187 of the **EU Financial Controls Annex**, which contains a governing screening restriction.

The PackSpec requires evidence for both `recovery-procedure` and `eu-screening-control`. Only the first is supplied. This is the same fictional case used in the [enterprise RAG training lab](../TRAINING.md).

```python
from qualityrag import evaluate

pack = {"id": "eu-recovery", "version": "1", "requirements": [
    {"id": "recovery-procedure"}, {"id": "eu-screening-control"}]}
evidence = [{"id": "pdf-74", "requirement_id": "recovery-procedure",
    "origin": "operations-handbook", "source_ref": "operations.pdf#page=74",
    "status": "SUPPORTS", "observed_at": "2026-11-02T10:00:00Z"}]
result = evaluate(pack, evidence, as_of="2026-11-02T10:05:00Z")
print(result["verdict"])  # INCONCLUSIVE
```

**Expected verdict:** `INCONCLUSIVE`. The recovery procedure is supported; the declared EU control remains unresolved. The application must not generate an unrestricted operational answer.

**Integration rule:** evaluate the trusted retrieval metadata on your server **before** invoking an LLM. Do not invent a supporting witness for a chunk that was not retrieved. Distinct source identifiers and timestamps do not establish authenticity.

**Scope:** This snippet calls the existing v0.1 metadata gate. It does not perform PDF extraction, semantic classification, or retrieval. Consult the [executable ingestion lab](../../examples/enterprise-rag/REAL-DOCUMENTS.md) for that separate demonstration.

## 4. Production integration checklist

- Keep the PackSpec server-owned and versioned.
- Supply provenance and timestamps from a trusted collector; never infer independence from two matching URLs alone.
- Block or defer model generation on both `REFUSE` and `INCONCLUSIVE`.
- Record sanitized findings and test with `conformance/v0.1.json`.

## 5. Compatibility & limitations

The base metadata gate is supported here. An extended ConstraintIR/WitnessGraph/Wgap compiler is also available as a separate experimental API. See [concepts](../concepts.md) for detailed semantics and limits.

## 6. Help & troubleshooting

If a run fails, consult [troubleshooting](../troubleshooting.md), then [support](../support.md). Include runtime version, sanitized inputs and exact result; never include confidential evidence in a public issue.

---

**Continue reading:** [All language SDKs](../README.md#choose-your-sdk) · [PackSpec reference](../concepts.md) · [Report an issue](https://github.com/cyrillesaxo/QualityRag/issues)
