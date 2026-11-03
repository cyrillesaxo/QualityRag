# Go — Four APX PackSpec-derived RAG examples

This guide uses **the same 12 cases** across the ten QualityRag SDKs, derived from the uploaded **SEMLOAN**, **Question Fan**, **FFI** and **software-selling** contracts. The source texts specify richer regimes than the v0.1 metadata gate can execute. These are **explicit educational projections**, not direct evaluation of the full original PackSpecs.

| Contract and example | Missing requirement | Expected |
| --- | --- | --- |
| SEMLOAN: learner praise without cold retrieval / transfer | `cold-retrieval-or-transfer` | `INCONCLUSIVE` |
| Question Fan: plausible question without decision consequence | `decision-consequence` | `INCONCLUSIVE` |
| FFI: source excerpt + probe but no corroboration | `independent-corroboration` | `INCONCLUSIVE` |
| Software selling: buyer interview + integration check without comparison | `controlled-comparison` | `INCONCLUSIVE` |

Each domain also has an `ADMIT` example (all declared evidence labels supplied) and a `REFUSE` example (an explicit contradictory witness). The following code checks **all 12** using the SDK. It does **not** call a retriever or LLM.

## SDK example

```go
// Run from a Go module that imports the local QualityRag SDK.
package main
import (
  "encoding/json"
  "fmt"
  "os"
  "time"
  q "github.com/cyrillesaxo/QualityRag/sdk/go"
)
func main() {
  var data struct {
    AsOf string `json:"as_of"`
    Scenarios []struct {
      ID string `json:"id"`
      Pack q.Pack `json:"pack"`
      Cases []struct {
        ID string `json:"id"`
        Expected string `json:"expected"`
        Evidence []q.Evidence `json:"evidence"`
      } `json:"cases"`
    } `json:"scenarios"`
  }
  raw, err := os.ReadFile("examples/apx-packspecs/fixtures.json"); if err != nil {panic(err)}
  if err=json.Unmarshal(raw,&data);err!=nil {panic(err)}
  asOf, err := time.Parse(time.RFC3339,data.AsOf);if err!=nil {panic(err)}
  for _,domain:=range data.Scenarios {
    for _,item:=range domain.Cases {
      decision,err:=q.Evaluate(domain.Pack,item.Evidence,asOf);if err!=nil {panic(err)}
      if decision.Verdict!=item.Expected {panic(domain.ID+"/"+item.ID)}
      fmt.Println(domain.ID,item.ID,decision.Verdict)
    }
  }
}
```

## Expected

For each domain, the fixture prints/verifies `INCONCLUSIVE`, `ADMIT`, and `REFUSE`. A non-`ADMIT` outcome must stop answer generation. A v0.1 `ADMIT` only means the declared **metadata obligations** were met, not that learning, research, or sales claims are certified.

Inspect [fixtures.json](../fixtures.json) and the [source-to-projection rationale](../README.md). Externalize the projected policy through the [PackSpec source-selection API](../../../docs/PACKSPEC-SOURCES.md): internal, JSON property, mounted JSON file, or Studio.

**Reference:** Cyrille Eloundou / [APX](https://apx.guide/).
