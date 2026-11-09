# QualityRag for Swift

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

> **SDK status:** Experimental · Source-built · Base evidence metadata gate available


## 1. Prerequisites & setup

Swift 5.9 and Swift Package Manager (macOS or compatible Swift toolchain). Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
cd sdk/swift && swift test
```

## 2. API reference

`Gate.evaluate(_ pack:Pack,_ evidence:[Witness],asOf:Date) -> Result`.

## 3. Example: incomplete retrieval from a large PDF corpus

An enterprise RAG search retrieves page 74 of a **Payments Operations Handbook** but misses page 187 of a governing **EU Financial Controls Annex**. The PackSpec declares both evidence obligations. Only the general procedure has a supporting witness.

```swift
import Foundation
import QualityRag
let pack = Pack("eu-recovery", "1", [
    Requirement("recovery-procedure"), Requirement("eu-screening-control")
])
let format = ISO8601DateFormatter()
let evidence = [Witness("pdf-74", "recovery-procedure",
    "operations-handbook", "operations.pdf#page=74", "SUPPORTS",
    format.date(from:"2026-11-02T10:00:00Z")!)]
let result = Gate.evaluate(pack, evidence,
    asOf:format.date(from:"2026-11-02T10:05:00Z")!)
print(result.verdict) // INCONCLUSIVE
```

**Expected verdict:** `INCONCLUSIVE`. The application must not invoke its answer-generating model until the missing obligation has been resolved. This is the v0.1 **metadata gate**; it does not retrieve or parse PDFs. See [enterprise training](../TRAINING.md) and [document ingestion](../../examples/enterprise-rag/REAL-DOCUMENTS.md).

## 4. Production integration checklist

- Keep the PackSpec server-owned and versioned.
- Supply provenance and timestamps from a trusted collector; never infer independence from two matching URLs alone.
- Block or defer model generation on both `REFUSE` and `INCONCLUSIVE`.
- Record sanitized findings and test with `conformance/v0.1.json`.

## 5. Compatibility & limitations

The base metadata gate is supported here. The advanced ConstraintIR/WitnessGraph/Wgap compiler is **not yet available** in this SDK. See [concepts](../concepts.md) for detailed semantics and limits.

## 6. Help & troubleshooting

If a run fails, consult [troubleshooting](../troubleshooting.md), then [support](../support.md). Include runtime version, sanitized inputs and exact result; never include confidential evidence in a public issue.

---

**Continue reading:** [All language SDKs](../README.md#choose-your-sdk) · [PackSpec reference](../concepts.md) · [Report an issue](https://github.com/cyrillesaxo/QualityRag/issues)
