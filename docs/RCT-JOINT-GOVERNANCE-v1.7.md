# RCT v1.7 — joint PackSpec and WitnessGraph diagnostics

This integration combines two **existing and independently sourced** governance evaluations:

- `tools/packspec_compiler/unified_gate.py`: reviewed, source-bound ConstraintIR evidence and bounded semantic checks, using the existing Python evidence SDK and host attestation requirement.
- `sdk/python/qualityrag/compiler.py`: compiled evidence requirements with origin-label WitnessGraph dependency groups and Wgap.

The research adapters live in:
- `tools/semantic_store/rct_packspec_bridge.py`
- `tools/semantic_store/rct_witness_bridge.py`
- `tools/semantic_store/rct_joint_governance.py`

The output contains both intact receipts, their fingerprints and a consolidated refusal or inconclusive diagnostic. **REFUSE dominates; neither subsystem can promote an RCT lens to ADMIT**. The unified gate's typed-IR source and the SDK evidence PackSpec source are *not assumed equal*: the source-to-policy correspondence must be independently reviewed and authenticated before any use requiring that trust.

## Demonstrated failure modes

- Two copies labeled as the same origin count as only one origin. Canonical WitnessGraph emits a dependent group and Wgap.
- A contradictory witness for a required or proposed-omission requirement forces REFUSE.
- Missing evidence leads to INCONCLUSIVE even when other evidence checks pass.
- All evidence requirements metadata-satisfied still yields RCT INCONCLUSIVE: adequate semantic coverage, genuinely independent witnesses, admissible omissions and source authenticity are unresolved.
- Changed fingerprints or altered bindings are rejected, never silently reinterpreted.

## Non-claims

This is a source-bound *diagnostic research integration*, not full PackSpec semantic compilation. A caller-authored origin label is not independent custody evidence. The canonical Python WitnessGraph lacks graph lineage edges beyond repeated-origin grouping. HCR, RCOC, WBC and FF-RCT are not implemented by this adapter, and signed review/attestation is not established. Do not claim that v1.7 validates omission safety.

The native policy SDK contains metadata-only `ADMIT` verdicts. Those describe supplied evidence metadata and **must not be represented as RCT admission**.

## Verification

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

The tests run both existing governance implementations, confirm origin dependency, deliberate contradictions, unmapped required/optional distinctions, stale binding rejection, and no generation.

The next milestone is a genuinely authenticated cross-source PackSpec map and a richer provenance graph using canonical APX evidence mechanisms when those implementations are available for public integration.
