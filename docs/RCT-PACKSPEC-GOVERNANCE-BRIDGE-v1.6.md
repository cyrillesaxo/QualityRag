# RCT v1.6 — canonical PackSpec governance bridge

This is the **first direct integration with the existing QualityRag unified gate**, not a second PackSpec evaluator. It imports `tools/packspec_compiler/unified_gate.py` and its `evaluate_unified` function. The gate, in turn, uses the existing evidence SDK and bounded semantic runtime.

## Operation

1. The creation-time RCT lens candidate remains immutable by fingerprint.
2. A caller creates an explicit *unverified binding* between the lens source and the original reviewed ConstraintIR source. They are different source identities; no hash equality is assumed.
3. The adapter validates the candidate's and binding's fingerprints and their independently scoped source IDs.
4. The existing unified gate evaluates all reviewed, source-bound IR nodes with supplied evidence witnesses, observations and an explicit `as_of` time. No host attestation verifier is supplied by this bridge.
5. Any canonical `REFUSE` remains `REFUSE`. All other results remain `INCONCLUSIVE`, since evidence/temporal/probe checks do not certify that semantic omissions preserve a purpose's meaning.
6. The `guarded_candidate_use` wrapper **never invokes a generator** in v1.6. This protects the critical gap: an existing PackSpec checked for evidence presence is not necessarily authority for the proposed RCT abstraction.

## Reproduce

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

- `tools/semantic_store/rct_packspec_bridge.py`
- `tools/semantic_store/tests/test_rct_packspec_bridge.py`

## Threat model and remaining gaps

The binding is caller-authored, not a cryptographically authenticated delegation. Neither the PackSpec reviewer identity nor the source/witness custody has been authenticated by this module. The adapter never makes a source-sufficiency assertion from an empty, missing or merely local receipt. Even if a host integration could produce a canonical unified-gate `ADMIT`, that *would not prove the new RCT lens preserves all necessary distinctions*, because the existing PackSpec clauses have not been semantically mapped to its omission contract. That mapping and its independent review must be explicit before any generated representation becomes production-usable.

Required next: bind reviewed PackSpec obligations to RCT purpose and preserved distinctions, verify independent WitnessGraph provenance, and enforce actual signed attestation with the existing gate while keeping verified omission sufficiency as a **separate** requirement. All omitted facts must be accessible through an immutable versioned original source, including FF-RCT reconstruction when integrated.

The research status is **candidate / INCONCLUSIVE**; this PR is not deployed.
