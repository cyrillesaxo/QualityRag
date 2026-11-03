# RCT + QualityRag — end-to-end research delivery

**Purpose:** a reproducible, fail-closed integration of typed grammar induction, purpose lenses, finite conservation, reversible structural representation, governed evidence and signed source custody. This is an **experimental research implementation**, not production-certified semantic governance, source truth or native FF-RCT.

**Lineage:** Cyrille Eloundou · [APX](https://apx.guide/).

## One-command demonstration

From the repository root (Python 3.12):

```bash
python -m pip install -r tools/packspec_compiler/requirements.txt
python tools/semantic_store/rct_demo.py
```

The output includes the induced typed AST, source/active-lens fact counts, dropped optional fact IDs, **all-pairs finite structural equivalence**, exact source reconstruction, and `qualityrag_admission: INCONCLUSIVE`. The demo uses synthetic facts only and never invokes a model generator.

## End-to-end inputs and execution

`tools/semantic_store/rct_end_to_end.py` provides:

- `run_structural_pipeline`: typed AST induction from separate training facts and labels, held-out positive/negative verification, purpose-contract creation, protected-witness lens contraction, exhaustive relation-pair conservation, lossless canonical source roundtrip, bounded witness-cover and optional source-revision drift.
- `attach_signed_governance`: diagnostic signed policy, witness provenance and source-custody evaluation; still no generation or admission.
- **`attach_reviewed_signed_governance`**: strict research integration requiring a separately signed reviewer mapping covering **every IR node**, required distinction and requested omitted fact, and the entire signed custody flow. It returns REFUSE for canonical contradictions and INCONCLUSIVE otherwise. A signed approval never proves semantic completeness.

The full signed test uses three separately trusted roles (policy, reviewer, evidence, and additionally custodian = **four key roles**), separate nonces and a durable SQLite replay ledger. No keys are embedded in the code.

## Actual implementation and honest acceptance matrix

| Work package | Delivered engineering evidence | Still not proven |
| --- | --- | --- |
| Semantic conservation | All result pairs for one declared bounded relation AST tested before/after lens contraction; held-out counterexamples reject | Universal meaning preservation, unknown-unknown sufficiency, or reasoning about arbitrary original prose |
| Source authority and PackSpec | Signed reviewed ConstraintIR and explicit node/omission binding, exact supplied source bytes checked against signed custody manifest | Actual publisher identity, legal/medical/regulatory authority and completeness of the original PackSpec |
| WitnessGraph provenance | Canonical Python WitnessGraph and Wgap, signed derivation DAG, shared-root collapse, mismatched-source/replay tests | Independent real-world provenance for distinct source roots and chain of custody outside the supplied records |
| WBC, HCR, RCOC | Bounded diagnostic candidates; optional **direct loader** for original APX TypeScript packages with no silent fallback; original HCR/RCOC receipt schemas preserved | Golden behavioral parity with private APX source in this repo CI; the native APX workspace must be separately built and configured |
| FF-RCT | Reversible multiscale reference frame, per-predicate and per-source summaries, compressed canonical bytes, strict hash-based reconstruction | The native FF-RCT grammar/codec, its physical model and independently validated efficiency |
| Economics | Lifecycle/update benchmark and matched mixed-operator benchmark vs indexed SQL and materialized SQL, with answer equality | Production-size realistic workloads, equal language runtimes, complete signed governance costs and a general speed advantage |
| Release/QA | Semantic Store, PackSpec compiler, Python SDK, native adapter transport, one-command demo and syntax checks in CI | Production tenant isolation, deployment, independent security review, semantic sign-off |

No matter how many local checks pass, this system **must not generate** from an experimental lens: every receipt retains `qualityrag_admission: INCONCLUSIVE`, except an explicit contradiction that yields `REFUSE`.

## Canonical APX integration

The **actual** algorithms are in `cyrillesaxo/apx`:

- `packages/apx-wbc`: `reduceToWMin` and `verifyWMin`
- `packages/apx-hcr`: `recoverConstraintFiber`
- `packages/apx-rcoc`: `compareSemanticAssuranceSnapshots`

`tools/semantic_store/rct_apx_native.mjs` is a direct dynamic adapter. It requires an absolute `APX_PACKAGES_ROOT` pointing to the original, separately built APX `packages` directory. Loading a missing package, malformed export or path escaping that root **fails closed**; no approximation is silently substituted. The WBC entrypoint requires a caller-owned, trusted synchronous decision oracle to preserve the actual host verdict. The adapter does not grant admission.

To execute this against canonical APX, the host must build the relevant TypeScript packages in its independently authorized private workspace. CI here tests the adapter transport against **interface stubs**, not native-algorithm parity. The original private source is not copied into QualityRag.

## Reproducible test commands

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py' -v
PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests -p 'test_*.py' -v
node --test tools/semantic_store/tests/test_rct_apx_native.mjs
python tools/semantic_store/rct_demo.py
```

For matched-query economics, from the root:

```bash
PYTHONPATH=tools/semantic_store python - <<'PY'
from rct_demo import fixture
from rct_matched_economics import run_matched_economics
training, training_labels=fixture('train-')
source, labels=fixture('held-')
grammar={'schema':'rct.typed-operator-grammar/v1.4',
         'predicate_types':{'p':['object','middle'],'q':['middle','target'],
                            'r':['object','target'],'context':['object','noise']},
         'operators':['EDGE','PATH','AND'],'max_ast_nodes':5,'max_candidates':500}
result=run_matched_economics(
    training,training_labels,source,labels,grammar,
    purpose='finite-classification-training',
    required_predicates=['p','q','r'],
    allowed_omission_predicates=['context'])
print(result['median_total_ns'])
print(result['matched_answer_equivalence'])
PY
```

The benchmark reports medians and does **not** assert RCT is faster. It includes Python induction, structural verification and reference reconstruction in RCT's total, but neither SQL nor RCT runs cryptographic governance in that timed comparison. No broad production conclusion is authorized.

## Safety and release boundary

Merge of this branch, if performed, means *experimental prototype code has passed its declared regression tests*, not that QualityRag can be publicly deployed as an authoritative evaluator. The actual source publisher/authority checks, native FF-RCT and native APX behavioral parity are external research dependencies. Until those are resolved, enterprise workflows must not interpret any research receipt as `ADMIT`.
