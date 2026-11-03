# Python — Five APX PackSpec-derived RAG examples
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

```python
import json
from pathlib import Path
from qualityrag import evaluate

data = json.loads(Path("examples/apx-packspecs/fixtures.json").read_text())
for domain in data["scenarios"]:
    for case in domain["cases"]:
        verdict = evaluate(domain["pack"], case["evidence"], as_of=data["as_of"])["verdict"]
        assert verdict == case["expected"], (domain["id"], case["id"], verdict)
        print(domain["id"], case["id"], verdict)
```

## Expected

For each domain, the fixture prints/verifies `INCONCLUSIVE`, `ADMIT`, and `REFUSE`. A non-`ADMIT` outcome must stop answer generation. A v0.1 `ADMIT` only means the declared **metadata obligations** were met, not that learning, research, or sales claims are certified.

Inspect [fixtures.json](../fixtures.json) and the [source-to-projection rationale](../README.md). Externalize the projected policy through the [PackSpec source-selection API](../../../docs/PACKSPEC-SOURCES.md): internal, JSON property, mounted JSON file, or Studio.

**Reference:** Cyrille Eloundou / [APX](https://apx.guide/).
