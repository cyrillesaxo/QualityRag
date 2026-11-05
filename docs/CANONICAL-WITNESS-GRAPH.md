# Original APX WitnessGraph grouping

US-007 now uses `buildWitnessGraph` from the original APX
`packages/apx-evidence/src/index.ts`, unmodified at commit
`9a4f8a3e4a3fe77d576369217525e54d0162b8b0`, under the existing Apache-2.0
vendoring terms. Its SHA-256 is
`49c690848c4dcb1022f815d5deb258ddd074317eb0cc3cebde40a99d069199ee`.

The previous claim that this source required an unavailable private package
was incorrect: the connected repository contains it at the same pinned APX
commit already used for WBC/RCoC.

The QualityRag adapter first resolves custody roots and transitive derivations.
It assigns one declared independence key to each overlapping-root component,
then executes original APX grouping through Node 24's TypeScript stripping.
The full original module is hash checked; request data is never compiled.

Returned nodes and dependent groups must agree exactly with the declared
root components. Missing/modified source, invalid input, unavailable runtime,
or discrepancies raise refusal rather than falling back to a Python substitute.
Both finite witness assessment and evidence projection perform this check.

`fixtures/canonical-witness-graph.json` pins a golden case; tests also cover
merged roots, duplicate IDs, changed/missing source and discrepancy refusal.

APX groups **declared independence keys**; it does not establish that those
keys or the underlying custodians are truthful or independent. Root discovery
remains the separately tested QualityRag adapter. No clinical truth, semantic
ADMIT, source authentication or FF-RCT parity is inferred.

```bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_native_witness.py' -v
```
