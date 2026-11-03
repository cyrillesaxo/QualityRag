# Composed native + signed source-span + typed-role governance

The role-binding stress dataset established that native APX lexical atoms alone fail to detect some substantive role/beneficiary changes. `tools/semantic_store/rct_native_semantic_host.py` now exposes `execute_relational_semantic_check` to compose three independent diagnostic paths over **identical original and candidate document versions**:

1. The **original native APX** bounded semantic-source comparator, executed in a restricted Node subprocess by the pre-existing host.
2. The **Ed25519-signed source-span obligation inventory**, validated against the governing reviewed ConstraintIR and durable nonce guard.
3. The **separately Ed25519-signed typed predicate-role-entity graph**, validated from exact source/candidate substrings and inventory digests against the same governing ConstraintIR.

Each reviewer key ID must be different from the policy key ID and from the other reviewer. The verifier preflights both signed payloads and document hashes **before** launching the native comparator or consuming any nonces. It then performs canonical signature/replay validation inside the existing signed source-span and role verifiers.

An observed `REFUSE` in **any** path dominates the combined decision. If every path is `INCONCLUSIVE`, the final decision remains `INCONCLUSIVE`. There is no `ADMIT`, `can_generate=true`, compression authorization, or implicit disclosure.

## Example expected behavior

For a reviewer-annotated payment fact:

```text
Source:    Alice must pay Bob.
Candidate: Bob must pay Alice.

PAY(OBLIGOR=Alice, BENEFICIARY=Bob)
  vs
PAY(OBLIGOR=Bob, BENEFICIARY=Alice)
```

The lexical APX comparator may return `INCONCLUSIVE` because its semantic atoms remain unchanged. The independently signed typed-role reviewer reports `REFUSE`, which becomes the combined diagnostic verdict. This is **explicit reviewer-annotated semantics**, not proof that an automated parser successfully inferred the relation.

A passive-voice reformulation with the **same reviewed** obligor and beneficiary remains `INCONCLUSIVE`, never a proof of general semantic equivalence.

## Test and remaining boundaries

```bash
python -m unittest discover -s tools/semantic_store/tests \
  -p 'test_rct_native_relational_governance.py' -v
```

The ordinary tests run real Ed25519 signatures, exact document digests, independent reviewer roles, durable nonce rejection, substituted annotation checks and a controlled **mock native interface**. They do not claim original private APX runtime execution.

Original native APX execution was separately demonstrated by [APX native run 41726055119](https://github.com/cyrillesaxo/apx/actions/runs/41726055119), which recorded 0/12 detection on the harder synthetic role-binding corpus.

A single fully signed production replay on an independently attested APX executable remains outstanding. The two review nonces are consumed sequentially, **not atomically**; a later failure may require fresh signed attestations. A signature on an annotation does not prove complete, truthful or independent semantic extraction.

The system continues to report `semantic_completeness=UNKNOWN`, `publisher_authority=NOT_ESTABLISHED`, and `native_runtime_authority=NOT_INDEPENDENTLY_ATTESTED`. Actual KBCT/12G cross-projection, independently validated source custody, true FF-RCT reconstruction and real-world expert-labeled evaluation are separate acceptance gates.
