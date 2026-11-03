# Ruby — Four APX PackSpec-derived QualityRag examples

Use the same 12 evidence-gate cases across SDKs, based on the uploaded **SEMLOAN v0.4.0**, **Question Fan v0.1.0**, **FFI v0.6.0**, and **Software-selling PackSpec v0.1.0**. These are *scoped training projections* for QualityRag metadata v0.1—not execution of the complete APX contracts.

| Domain | Initial incomplete RAG evidence | Gate |
| --- | --- | --- |
| SEMLOAN | Learner praises lesson; no verified cold retrieval / transfer | `INCONCLUSIVE` |
| Question Fan | Candidate question lacks documented decision consequence | `INCONCLUSIVE` |
| FFI | Source excerpt and probe present; independent corroboration missing | `INCONCLUSIVE` |
| Software selling | Buyer pain and technical prerequisites present; no controlled comparison | `INCONCLUSIVE` |

For each domain, the [shared fixture](../fixtures.json) also supplies an `ADMIT` case and a `REFUSE` case. The snippet below checks all 12. An `ADMIT` confirms only the declared **evidence metadata categories**—it does **not** certify learning, investigation quality, sales effectiveness, or regulatory compliance.

## SDK example

```ruby
# Run from repo root; Ruby standard library JSON.
require "json"
require "time"
require_relative "../../../sdk/ruby/lib/qualityrag"

data=JSON.parse(File.read("examples/apx-packspecs/fixtures.json"))
data["scenarios"].each do |domain|
  domain["cases"].each do |item|
    result=QualityRag.evaluate(domain["pack"], item["evidence"], as_of:Time.iso8601(data["as_of"]))
    raise "Unexpected verdict" unless result["verdict"]==item["expected"]
    puts "#{domain["id"]} #{item["id"]} #{result["verdict"]}"
  end
end
```

If using an external PackSpec, load the projected JSON through [the source-selection API](../../../docs/PACKSPEC-SOURCES.md) before passing it to this SDK. Policy loading errors and all non-`ADMIT` verdicts must stop answer generation; never silently fall back to another source.

See [source-to-projection design and limitations](../README.md). Conceptual attribution: **Cyrille Eloundou — [APX](https://apx.guide/)**.
