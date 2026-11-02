# QualityRag for Rust

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

## Prerequisites and onboarding

Stable Rust toolchain and Cargo; chrono is a dependency. Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
cd sdk/rust && cargo test
```

## API

`qualityrag::evaluate(&Pack,&[Evidence],DateTime<Utc>) -> Result`.

## First decision

```rust
use chrono::{DateTime,Utc};
use qualityrag::{evaluate,Pack,Requirement};
let pack = Pack{id:"demo".into(),version:"1".into(),requirements:vec![Requirement{id:"r".into(),min_independent_sources:2,max_age_seconds:None}]};
let now: DateTime<Utc> = "2026-11-02T10:05:00Z".parse().unwrap();
assert_eq!(evaluate(&pack,&[],now).verdict,"INCONCLUSIVE");
```

The empty evidence array does not satisfy two independent sources; the expected decision is `INCONCLUSIVE`. These snippets show API usage from the repository source tree; they are not package-registry installation commands. Import paths assume the corresponding local module/project is built or referenced in your application.

## Integration checklist

- Keep the PackSpec server-owned and versioned.
- Supply provenance and timestamps from a trusted collector; never infer independence from two matching URLs alone.
- Block or defer model generation on both `REFUSE` and `INCONCLUSIVE`.
- Record sanitized findings and test with `conformance/v0.1.json`.

## Compatibility

The base metadata gate is supported here. The advanced ConstraintIR/WitnessGraph/Wgap compiler is **not yet available** in this SDK. See [concepts](../concepts.md) for detailed semantics and limits.

## Help

If a run fails, consult [troubleshooting](../troubleshooting.md), then [support](../support.md). Include runtime version, sanitized inputs and exact result; never include confidential evidence in a public issue.
