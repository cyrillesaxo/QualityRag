# APX PackSpec examples for every QualityRag SDK

**Status:** executable *metadata-gate projections* of five user-supplied APX PackSpec artifacts; these are **not** full implementations of those PackSpecs. Attribution: **Cyrille Eloundou / APX research — [apx.guide](https://apx.guide/)**.

## Why projection is necessary

The uploaded originals are rich contracts: some define learning states and field outcomes, others describe question selection, witness graphs, forensic probes, or a sales-validation depth ladder. QualityRag SDK v0.1 expects only `{id, version, requirements:[{id, min_independent_sources?, max_age_seconds?}]}` plus witness metadata; directly passing the full YAML/PDF/text as a PackSpec would misrepresent what the SDK checks.

The `fixtures.json` file contains **five deliberately scoped v0.1 policies** with source provenance and **15 witnessed outcomes** (5 domains × 3 cases). In `ADMIT`, the *declared evidence categories* were represented; it does **not** certify a learner, research claim or sales result, nor enforce semantic constraints contained in the original source.

| Original APX source | Representative business decision | Missing evidence → INCONCLUSIVE | Contradiction → REFUSE | Matched metadata → ADMIT |
| --- | --- | --- | --- | --- |
| **SEMLOAN v0.4.0** (uploaded YAML) | May an education service claim learning convergence? | No independent cold retrieval/transfer | Learner attempt provenance contradicted by an AI shortcut | Attempt provenance plus retrieval/transfer evidence present |
| **Question Fan v0.1.0** (uploaded text) | May a generated optional question be surfaced? | No decision consequence tied to the challenged assumption | Evidence rejects the claimed consequence | Objective, assumption, consequence metadata present |
| **FFI v0.6.0** (uploaded PDF) | May recovered constraints be presented as supported? | No independent corroboration | Discriminating probe contradicts a claim | Custody, probe, corroboration all represented |
| **FFI Teacher Transformation** (uploaded education PDF) | May the instructional output claim cross-platform transfer? | Missing framework-swap back-translation probe | Cross-platform probe disproves the claim | W_min, prerequisite map, atomic artifact and transfer-check metadata present |
| **Software-selling PackSpec v0.1.0** (uploaded PDF) | May a pilot-backed value claim proceed? | No controlled rival/baseline comparison | Comparative test contradicts claim | Buyer state, prerequisites, comparison present |

These are **training hypotheticals**. The uploaded education PDF is FFI's teacher-transformation addendum and is modeled separately from the longer FFI investigation specification. For example, SEMLOAN only recognizes cold retrieval/transfer as a learning-confirming FieldOutcome; the fixture's `ADMIT` is *not* a substitute for checking actual learner generation, time separation, or transfer validity. The Question Fan additionally requires explicit user choice for investigation, a zero-fan route, and no more than three eligible questions; those are outside the base gate. FFI's custody, deception screening and evidence independence also require verification beyond caller-provided origin strings.

## Run externally loaded PackSpecs

The [external policy guide](EXTERNAL-POLICIES.md) provides standalone JSON PackSpecs for all five scenarios, demonstrates file and property loading, and tests that all fifteen decisions remain identical regardless of which source is selected. These are narrow training projections, not the full APX contracts.

## Run the shared fixture tests

```bash
PYTHONPATH=sdk/python python -m unittest discover -s examples/apx-packspecs -p 'test_*.py'
```

The following language pages show the corresponding SDK API over the same four domains. In each page, the executable snippet deliberately uses the **missing-evidence** case (expect `INCONCLUSIVE`); the JSON fixtures also supply `ADMIT` and `REFUSE` variations.

- [Java](languages/java.md)
- [Python](languages/python.md)
- [Typescript](languages/typescript.md)
- [Go](languages/go.md)
- [C#](languages/csharp.md)
- [Rust](languages/rust.md)
- [Kotlin](languages/kotlin.md)
- [Php](languages/php.md)
- [Ruby](languages/ruby.md)
- [Swift](languages/swift.md)

## Integration boundaries

* Source selection: keep these projected policies in code, a JSON property/file, or Studio via the [PackSpec source-selection guide](../../docs/PACKSPEC-SOURCES.md).
* Guard the LLM invocation server-side; missing source or `INCONCLUSIVE/REFUSE` must not trigger generation.
* Do not infer that repeated excerpts from the same document are independent.
* Preserve original PackSpec provenance and version. The projections are educational artifacts, not replacements for original YAML/PDF governance.
* The education PDF was recovered from the uploaded-file index. It describes FFI Phase T / teacher_accelerated, including W_min, B4, G9, E2 and cross-platform back-translation. The fixture models only four declarative evidence categories from that specification; it does not run the teacher engine.
