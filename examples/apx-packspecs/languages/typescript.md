# Typescript — Five APX PackSpec-derived RAG examples
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

```typescript
// Node.js 20+; build the TypeScript SDK first: npm --prefix sdk/typescript run build
import { readFileSync } from "node:fs";
import { evaluate, type PackSpec, type Evidence } from "@qualityrag/sdk";

type Case = { id: string; expected: string; evidence: Evidence[] };
type Domain = { id: string; pack: PackSpec; cases: Case[] };
const fixture = JSON.parse(readFileSync("examples/apx-packspecs/fixtures.json", "utf8"));
for (const domain of fixture.scenarios as Domain[]) {
  for (const item of domain.cases) {
    const verdict = evaluate(domain.pack, item.evidence, fixture.as_of).verdict;
    if (verdict !== item.expected) throw new Error(domain.id + "/" + item.id);
    console.log(domain.id, item.id, verdict);
  }
}
```

## Expected

For each domain, the fixture prints/verifies `INCONCLUSIVE`, `ADMIT`, and `REFUSE`. A non-`ADMIT` outcome must stop answer generation. A v0.1 `ADMIT` only means the declared **metadata obligations** were met, not that learning, research, or sales claims are certified.

Inspect [fixtures.json](../fixtures.json) and the [source-to-projection rationale](../README.md). Externalize the projected policy through the [PackSpec source-selection API](../../../docs/PACKSPEC-SOURCES.md): internal, JSON property, mounted JSON file, or Studio.

**Reference:** Cyrille Eloundou / [APX](https://apx.guide/).
