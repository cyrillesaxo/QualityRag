# C# — Five APX PackSpec-derived RAG examples
| FFI Teacher Transformation | Teaching content has not passed the cross-framework back-translation check | `INCONCLUSIVE` |

This guide uses **the same 15 cases** across the ten QualityRag SDKs, derived from the uploaded **SEMLOAN**, **Question Fan**, **FFI**, **FFI Teacher Transformation (education)** and **software-selling** contracts. The source texts specify richer regimes than the v0.1 metadata gate can execute. These are **explicit educational projections**, not direct evaluation of the full original PackSpecs.

| Contract and example | Missing requirement | Expected |
| --- | --- | --- |
| SEMLOAN: learner praise without cold retrieval / transfer | `cold-retrieval-or-transfer` | `INCONCLUSIVE` |
| Question Fan: plausible question without decision consequence | `decision-consequence` | `INCONCLUSIVE` |
| FFI: source excerpt + probe but no corroboration | `independent-corroboration` | `INCONCLUSIVE` |
| FFI Teacher Transformation: tutorial lacks cross-platform probe | `cross-platform-back-translation` | `INCONCLUSIVE` |
| Software selling: buyer interview + integration check without comparison | `controlled-comparison` | `INCONCLUSIVE` |

Each domain also has an `ADMIT` example (all declared evidence labels supplied) and a `REFUSE` example (an explicit contradictory witness). The following code checks **all 15** using the SDK. It does **not** call a retriever or LLM.

## SDK example

```csharp
// C# 12/.NET 8; reference sdk/csharp/QualityRag/QualityRag.csproj.
using System.Text.Json;
using QualityRag;

using var doc = JsonDocument.Parse(File.ReadAllText("examples/apx-packspecs/fixtures.json"));
var root=doc.RootElement;
var asOf=DateTimeOffset.Parse(root.GetProperty("as_of").GetString()!);
foreach(var domain in root.GetProperty("scenarios").EnumerateArray()) {
    var raw=domain.GetProperty("pack");
    var pack=new Pack(raw.GetProperty("id").GetString()!,raw.GetProperty("version").GetString()!,
        raw.GetProperty("requirements").EnumerateArray()
            .Select(x=>new Requirement(x.GetProperty("id").GetString()!)).ToArray());
    foreach(var item in domain.GetProperty("cases").EnumerateArray()) {
        var witnesses=item.GetProperty("evidence").EnumerateArray().Select(x=>new Witness(
            x.GetProperty("id").GetString()!,x.GetProperty("requirement_id").GetString()!,
            x.GetProperty("origin").GetString()!,x.GetProperty("source_ref").GetString()!,
            x.GetProperty("status").GetString()!,
            DateTimeOffset.Parse(x.GetProperty("observed_at").GetString()!))).ToArray();
        var verdict=Gate.Evaluate(pack,witnesses,asOf).Verdict;
        if(verdict!=item.GetProperty("expected").GetString()) throw new Exception("Wrong verdict");
        Console.WriteLine($"{domain.GetProperty("id")} {item.GetProperty("id")} {verdict}");
    }
}
```

## Expected

For each domain, the fixture prints/verifies `INCONCLUSIVE`, `ADMIT`, and `REFUSE`. A non-`ADMIT` outcome must stop answer generation. A v0.1 `ADMIT` only means the declared **metadata obligations** were met, not that learning, research, or sales claims are certified.

Inspect [fixtures.json](../fixtures.json) and the [source-to-projection rationale](../README.md). Externalize the projected policy through the [PackSpec source-selection API](../../../docs/PACKSPEC-SOURCES.md): internal, JSON property, mounted JSON file, or Studio.

**Reference:** Cyrille Eloundou / [APX](https://apx.guide/).
