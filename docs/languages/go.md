# QualityRag for Go

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

> **SDK status:** Experimental · Source-built · Base evidence metadata gate available


## 1. Prerequisites & setup

Go 1.22 or later; no third-party runtime dependency. Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
cd sdk/go && go test ./...
```

## 2. API reference

`qualityrag.Evaluate(pack, witnesses, time.Time)` returns `(Result,error)`.

## 3. First decision

```go
package main
import ("fmt"; "time"; q "github.com/cyrillesaxo/QualityRag/sdk/go")
func main() {
 p := q.Pack{ID:"demo",Version:"1",Requirements:[]q.Requirement{{ID:"r",MinIndependentSources:2}}}
 result,err := q.Evaluate(p,[]q.Evidence{},time.Date(2026,11,2,10,5,0,0,time.UTC))
 if err != nil {panic(err)}
 fmt.Println(result.Verdict) // INCONCLUSIVE
}
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
