# Rust — Four APX PackSpec-derived QualityRag examples

Use the same 12 evidence-gate cases across SDKs, based on the uploaded **SEMLOAN v0.4.0**, **Question Fan v0.1.0**, **FFI v0.6.0**, and **Software-selling PackSpec v0.1.0**. These are *scoped training projections* for QualityRag metadata v0.1—not execution of the complete APX contracts.

| Domain | Initial incomplete RAG evidence | Gate |
| --- | --- | --- |
| SEMLOAN | Learner praises lesson; no verified cold retrieval / transfer | `INCONCLUSIVE` |
| Question Fan | Candidate question lacks documented decision consequence | `INCONCLUSIVE` |
| FFI | Source excerpt and probe present; independent corroboration missing | `INCONCLUSIVE` |
| Software selling | Buyer pain and technical prerequisites present; no controlled comparison | `INCONCLUSIVE` |

For each domain, the [shared fixture](../fixtures.json) also supplies an `ADMIT` case and a `REFUSE` case. The snippet below checks all 12. An `ADMIT` confirms only the declared **evidence metadata categories**—it does **not** certify learning, investigation quality, sales effectiveness, or regulatory compliance.

## SDK example

```rust
// Add this as a Rust example within sdk/rust; dependencies: serde_json, chrono.
use chrono::{DateTime, Utc};
use qualityrag::{evaluate, Evidence, Pack, Requirement};
use serde_json::Value;
let data: Value = serde_json::from_str(
    &std::fs::read_to_string("../../examples/apx-packspecs/fixtures.json").unwrap()).unwrap();
let as_of: DateTime<Utc> = data["as_of"].as_str().unwrap().parse().unwrap();
for domain in data["scenarios"].as_array().unwrap() {
    let raw=&domain["pack"];
    let pack=Pack{id:raw["id"].as_str().unwrap().into(),
        version:raw["version"].as_str().unwrap().into(),
        requirements:raw["requirements"].as_array().unwrap().iter().map(|r|Requirement{
            id:r["id"].as_str().unwrap().into(), min_independent_sources:1,max_age_seconds:None
        }).collect()};
    for case in domain["cases"].as_array().unwrap(){
        let evidence: Vec<Evidence>=case["evidence"].as_array().unwrap().iter().map(|e|Evidence{
            id:e["id"].as_str().unwrap().into(),
            requirement_id:e["requirement_id"].as_str().unwrap().into(),
            origin:e["origin"].as_str().unwrap().into(),
            source_ref:e["source_ref"].as_str().unwrap().into(),
            status:e["status"].as_str().unwrap().into(),
            observed_at:e["observed_at"].as_str().unwrap().into()
        }).collect();
        let result=evaluate(&pack,&evidence,as_of);
        assert_eq!(result.verdict,case["expected"].as_str().unwrap());
        println!("{} {} {}",domain["id"],case["id"],result.verdict);
    }
}
```

If using an external PackSpec, load the projected JSON through [the source-selection API](../../../docs/PACKSPEC-SOURCES.md) before passing it to this SDK. Policy loading errors and all non-`ADMIT` verdicts must stop answer generation; never silently fall back to another source.

See [source-to-projection design and limitations](../README.md). Conceptual attribution: **Cyrille Eloundou — [APX](https://apx.guide/)**.
