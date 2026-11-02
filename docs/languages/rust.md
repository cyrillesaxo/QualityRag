# QualityRag for Rust

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

> **SDK status:** Experimental · Source-built · Base evidence metadata gate available


## 1. Prerequisites & setup

Stable Rust toolchain and Cargo; chrono is a dependency. Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
cd sdk/rust && cargo test
```

## 2. API reference

`qualityrag::evaluate(&Pack,&[Evidence],DateTime<Utc>) -> Result`.

## 3. First decision

```rust
use chrono::{DateTime,Utc};
use qualityrag::{evaluate,Pack,Requirement};
let pack = Pack{id:"demo".into(),version:"1".into(),requirements:vec![Requirement{id:"r".into(),min_independent_sources:2,max_age_seconds:None}]};
let now: DateTime<Utc> = "2026-11-02T10:05:00Z".parse().unwrap();
assert_eq!(evaluate(&pack,&[],now).verdict,"INCONCLUSIVE");
```

The empty evidence array does not satisfy two independent sources; the expected decision is `INCONCLUSIVE`. These snippets show API usage from the repository source tree; they are not package-registry installation commands. Import paths assume the corresponding local module/project is built or referenced in your application.

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
