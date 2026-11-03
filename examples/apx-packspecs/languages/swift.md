# Swift — Four APX PackSpec-derived QualityRag examples

Use the same 12 evidence-gate cases across SDKs, based on the uploaded **SEMLOAN v0.4.0**, **Question Fan v0.1.0**, **FFI v0.6.0**, and **Software-selling PackSpec v0.1.0**. These are *scoped training projections* for QualityRag metadata v0.1—not execution of the complete APX contracts.

| Domain | Initial incomplete RAG evidence | Gate |
| --- | --- | --- |
| SEMLOAN | Learner praises lesson; no verified cold retrieval / transfer | `INCONCLUSIVE` |
| Question Fan | Candidate question lacks documented decision consequence | `INCONCLUSIVE` |
| FFI | Source excerpt and probe present; independent corroboration missing | `INCONCLUSIVE` |
| Software selling | Buyer pain and technical prerequisites present; no controlled comparison | `INCONCLUSIVE` |

For each domain, the [shared fixture](../fixtures.json) also supplies an `ADMIT` case and a `REFUSE` case. The snippet below checks all 12. An `ADMIT` confirms only the declared **evidence metadata categories**—it does **not** certify learning, investigation quality, sales effectiveness, or regulatory compliance.

## SDK example

```swift
// Add this to a Swift executable target that depends on QualityRag.
import Foundation
import QualityRag

let data=try Data(contentsOf:URL(fileURLWithPath:"examples/apx-packspecs/fixtures.json"))
let root=try JSONSerialization.jsonObject(with:data) as! [String:Any]
let clock=ISO8601DateFormatter()
let asOf=clock.date(from:root["as_of"] as! String)!
for domain in root["scenarios"] as! [[String:Any]] {
    let raw=domain["pack"] as! [String:Any]
    let requirements=(raw["requirements"] as! [[String:Any]]).map {
        Requirement($0["id"] as! String)
    }
    let pack=Pack(raw["id"] as! String,raw["version"] as! String,requirements)
    for item in domain["cases"] as! [[String:Any]] {
        let evidence=(item["evidence"] as! [[String:Any]]).map { e in
            Witness(e["id"] as! String,e["requirement_id"] as! String,
                e["origin"] as! String,e["source_ref"] as! String,e["status"] as! String,
                clock.date(from:e["observed_at"] as! String)!)
        }
        let verdict=Gate.evaluate(pack,evidence,asOf:asOf).verdict
        precondition(verdict==item["expected"] as! String)
        print(domain["id"]!,item["id"]!,verdict)
    }
}
```

If using an external PackSpec, load the projected JSON through [the source-selection API](../../../docs/PACKSPEC-SOURCES.md) before passing it to this SDK. Policy loading errors and all non-`ADMIT` verdicts must stop answer generation; never silently fall back to another source.

See [source-to-projection design and limitations](../README.md). Conceptual attribution: **Cyrille Eloundou — [APX](https://apx.guide/)**.
