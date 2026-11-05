# Functional Evidence and Obligation Discovery (experimental v0.1)

This is an advisory search module, **not** an alternate QUALITYRAG evaluator.
It reuses `qualityrag.compiler.compile_pack` and `evaluate_compiled` to determine
which approved obligations are unresolved. The canonical reviewed ConstraintIR
and `tools/packspec_compiler/unified_gate.py` remain responsible for admission.

## Behavior

- Traverse caller-supplied entity/edge graphs using typed relations such as
  `IS_A`, `PART_OF`, `CONTAINS`, `FUNCTIONAL_SIBLING`, `EXCEPTS`,
  `REQUIRES` and `SUPERSEDES`.
- Produce **unverified retrieval targets** only for unresolved requirements.
- Flag known scope/authority mismatch; mismatch is not an authorization.
- Suggest possible additional policy obligations on `EXCEPTS`, `REQUIRES`,
  and `SUPERSEDES` edges, always marked `REVIEW_REQUIRED`.
- Record paths and source reference labels, SHA-256 of the supplied pack and
  graph, traversal budget, and the existing evaluator's baseline verdict.
- A satisfied declared obligation does not imply the PackSpec is complete.
- **Never edit a PackSpec, generate an answer, forge an evidence witness,
  authenticate lineage, certify a functional sibling, or issue ADMIT.**

## Python example

```python
from qualityrag.discovery import discover

pack = {"id": "sample", "version": "1", "requirements": [
    {"id": "regulation", "min_independent_sources": 1, "scope": "GA",
     "authority": "official"}]}
graph = {
  "nodes": [
    {"id": "rule", "source_ref": "doc:rule", "scope": "GA"},
    {"id": "exception", "source_ref": "doc:exception", "scope": "GA",
     "authority": "official", "proposed_requirement_id": "exception_check"}],
  "edges": [{"source": "rule", "target": "exception",
             "relation": "EXCEPTS", "source_ref": "doc:rule"}]
}
receipt = discover(pack, [], graph,
                   [{"requirement_id": "regulation", "entity_id": "rule"}],
                   as_of="2026-11-05T10:00:00Z")
assert receipt["discovery_verdict"] == "INCONCLUSIVE"
assert receipt["can_generate"] is False
```

## Security and governance

Treat all graph nodes, edges, labels, source references and candidate policy
amendments as untrusted data. A source_ref is only a search/provenance hint.
Callers must independently retrieve, authenticate, verify applicability and
reconcile provenance before presenting new witnesses to the **existing unified
gate**. Any amendment must go through the normal reviewed PackSpec/IR workflow.
Do not give this module the capability to mutate the policy registry.

The traversal is directed, bounded (`max_depth <= 5`, `max_candidates <= 100`,
500 nodes and 2,000 edges) and deterministic for a fixed input. The current
`max_candidates` bound limits result count, **not total graph inspection**;
the static edge bound caps work. This stage does not implement calibrated
RCT expected-value ranking, authenticated WitnessGraph lineage, live retrieval,
cross-language parity or autonomous Garden promotion. Those require separate,
evidence-backed milestones.

## Tests

```bash
PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests -p 'test_*.py'
```

## Next milestones

1. Connect candidate retrieval to an authenticated host retrieval adapter.
2. Bind recovered evidence to a reviewed PackSpec/ConstraintIR and verify
   WitnessGraph custody with the existing unified gate.
3. Add conservative RCT search ranking with measured search and verification
   cost and explicit abstention.
4. Compare baseline retrieval, typed traversal and functional-sibling expansion
   on frozen PackSpecs, held-out questions and deceptive witness controls.
5. Promote only independently reviewed relations and policy changes.
