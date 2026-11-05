# Joint grammar + activation scan and first repair (research v0.1)

**Scope:** QualityRag `tools/semantic_store`. This is a bounded integration
slice for the Semantic Garden's co-evolution hypothesis, **not** the finished
autonomous Garden, an FF-RCT implementation, or an authorized PackSpec gate.

## Code scan — gaps found

| Area | Verified existing implementation | Gap | This change |
| --- | --- | --- | --- |
| Typed grammar | `rct_synthesis.py`, `rct_typed_grammar.py` | Candidate grammar and activation optimized independently | Compare grammar/activation pairs |
| Activation | Purpose lenses and precomputed indexes | No explicit selectable activation regime or source-bound activation signals | LAZY, EAGER_WORKLOAD, EAGER_ALL with source-version signals |
| Fidelity | `rct_reference_frame.py` | Optimization benchmarks did not jointly verify reconstruction with each activation policy | Exact canonical reconstruction in both phases |
| Cross-regime evaluation | `rct_lifecycle.py` | No paired 2D grammar × activation cost matrix | Six paired candidate strategies |
| Verification | Existing finite graph checks | Risk of checking only activated positive examples | Independent SQL comparison over all feasible subjects |
| Update lifecycle | One-source-mutation tests | Potential to reuse stale caches or active indexes after revisions | Rebuild per source SHA and verify changed answer digest |
| Research selection | Candidate and lifecycle comparisons | Risk of promoting a single noisy winner | Pareto research candidates only; champion remains `null` |
| Assurance | Experimental custody, PackSpec, D15, native APX adapters | No full authenticated or canonical FF-RCT co-evolution gate | Remains explicitly `INCONCLUSIVE` |

## Operation

`evaluate_joint_search(training, source, updated_source, workload, trials=3)`

1. Compile the bounded predicate pair from **separate training data** using
   the already existing `propose_compositions`.
2. Compare direct fact grammar and a preprogrammed two-hop composed grammar.
3. Compare lazy activation, eagerly activated workload subjects, and global
   eager activation for each grammar.
4. For **each** variant and source revision: store the reversible reference
   frame, reconstruct exact source, materialize the grammar, activate the
   selected subjects, execute the identical query budget, then independently
   verify every graph subject with SQL.
5. Record creation, activation, query, reconstruction and verification time,
   plus serialized reference-frame and active-index/cache bytes.
6. Return median research measurements and nondominated cost/size candidates.
   No production champion or generation/admission is enabled.

The source revision is an input snapshot, not an automatic watch/notification.
Caches are recreated per SHA. The original source retains all facts including
those irrelevant to the activated query.

### Reproduce

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_rct_joint_optimizer.py' -v
```

The existing `apx-semantic-store.yml` PR workflow also runs all Semantic Store
tests, compilation and the native transport/fail-closed regressions.

## Scientific limits (material)

- The two grammars are **known, programmed representations**; the Garden does
  not autonomously invent any new operator here.
- The three activation policies are static and the query signals are supplied.
  No learned activation policy or self-directed experiment loop yet.
- `rct_reference_frame.py` is a zlib-based reversible **reference codec**,
  **not native FF-RCT**; source fidelity alone does not establish
  preservation of purpose-relative semantics.
- The comparison is Python candidate implementations against an independent
  SQLite structural oracle, not fair full-lifecycle economics versus both
  production-class SQL direct and incrementally maintained materialized views.
- Serialized sizes are inspectable byte proxies, not measured resident memory,
  GPU load, energy, network or durable disk costs.
- An SQL oracle is an independent *algorithmic* check, not independent source
  custody, document truth, policy authority or epistemic channel independence.
- No canonical authenticated k/b/c/τ, FF-RCT, FFI, HCR/RCOC, WBC, D15, CUS,
  TERM, or QualityRag PackSpec admission is attached. All candidates remain
  `INCONCLUSIVE` and `can_generate=false`.
- Timing noise, synthetic data and small samples prohibit general claims of
  superiority. Compare negative controls and realistic workloads before
  considering a learned or promoted policy.

## Remaining P0 steps for the actual Semantic Garden

1. Locate and connect the live Garden research-event ledger and operator
   experiment orchestration; its screenshot alone is not source code.
2. Replace the reference frame with the **canonical native FF-RCT encoder and
   decoder** and record real activation/decoder resource costs.
3. Generate grammar operators and activation policies from experimental failure
   hypotheses (functional siblings, RCOC/HCR), not fixed enumerated choices.
4. Integrate purpose-relative PackSpec, WitnessGraph provenance and explicit
   D15 adversarial stress; preserve k/b/c/τ and TERM receipts.
5. Use a frozen held-out benchmark, including hard negative-transfer families,
   against direct SQL, incremental SQL and appropriate codec/model baselines.
6. Add reviewed, versioned promotion and demotion, replay on dependency change,
   and rollback without destroying research lineage.


## Running the executable comparison

```bash
python tools/semantic_store/rct_joint_demo.py --trials 3 --output /tmp/joint-search-receipt.json
```

The demonstration constructs separate training/source snapshots, mutates an
original relation, verifies full source reconstruction on both versions,
runs the six grammar/activation configurations, and prints measured research
costs and a Pareto set. It uses synthetic, deliberately small graphs.

## Research memory integration (existing ledger)

`rct_joint_ledger.append_joint_research(db, receipt, evidence_uri=..., actor=...)`
stores the receipt's experiment assertion and hash in
`tools/research_ledger/ledger.py` using its existing append-only claim,
measurement and assessment primitives. It refuses altered fingerprints,
missing/incomplete candidates or any attempt to replace `INCONCLUSIVE`
with an admission. These events do not promote production policies.

The adapter currently calls several existing ledger write functions
sequentially. A process crash between them can leave a partial local
research record; atomic transaction semantics and recovery require a
separate canonical ledger API revision before production use.

## Further gap: integration with the visual Semantic Gardener

The current repository scan did not locate a verified implementation path
for the visual Garden event UI shown in the conversation. This PR adds
measured semantic-store experiments and ledger receipts, **not** a live
connection to that UI. The UI's actual repository/API must be verified
before integrating interactive branch/replay/promotion actions.

## Next research increment: bounded co-evolution

`tools/semantic_store/rct_garden_coevolution.py` expands the earlier
two-hop-only grammar into a **data-mined, variable-length (2–4 hop)
composition candidate**. This is a genuinely broader candidate space,
but it is still within the predeclared `RELATION_PATH_COMPOSITION` family;
it is **not** evidence of inventing arbitrary new mathematical operators.

`induce_from_examples` accepts positive and adversarial negative examples
that reference **training nodes only** and selects a path only if a unique
candidate fits all of them. If multiple paths remain consistent, it emits
`AMBIGUOUS` and requests a discriminating probe instead of choosing one.

`run_investigation` then freezes the chosen path and evaluates it across
two separately versioned source snapshots. The holdout workload cannot
inject its own predicate path. An independent SQLite reference query
checks all feasible subjects, not only the positive examples.

Activation signals are derived from the workload frequency distribution:
on-demand, frequency-aware prefetch, or all-subject prefetch. Each policy
records activation, representation, query, verification and reference
reconstruction costs. The Garden returns candidate measurements, never an
admitted champion or an authorized policy change.

### Validate the new experiment

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_rct_garden_*.py' -v
```

### Not yet implemented

This research loop is synchronous and bounded; it does not autonomously
schedule background investigations. It cannot invent entirely new
operator *families*, evolve decoder code, execute canonical native FF-RCT,
or promote reasoning kernels into production. The experimental operators
and activation signals require held-out stress and full RCT/FFI/PackSpec
authority before any broader scientific claim.

In particular, `UNIQUE_TRAINING_HYPOTHESIS` means only that one
predeclared operator **fits the observed training examples**. It does not
establish semantic truth, k4 transfer, independent witness channels,
or superiority to a native graph/SQL engine.
