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
on-demand, frequency-aware prefetch, or all-subject prefetch. Each is
paired with two compiled representation forms: direct graph traversal and
materialized multi-hop composition. This produces six experiments per
training-selected operator, rather than merely six labels on identical code.
Every candidate records representation, activation, query, verification and
reference reconstruction costs. The Garden returns candidate measurements, never an
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

### Execute the co-evolution demo

```bash
python tools/semantic_store/rct_garden_demo.py --trials 3 --output /tmp/garden-research.json
```

This demo first selects the three-hop composition operator from **training
examples only**, with a negative control. The evaluation source and revised
source remain separate. It then pairs the learned candidate with two actual
representation implementations (direct and materialized) and three activation
strategies. Results are research candidates, not a new system capability claim.

If training examples are ambiguous, the operator is **not** selected; the
investigation yields a request for discriminating probes. The current
implementation does not yet automatically generate or execute those probes.

### Ambiguity and adversarial probing

When multiple induced grammar paths fit the positive **and negative**
training observations, the research kernel now abstains. It searches the
bounded training graph for an unobserved subject/target query on which the
candidate operators disagree and records that as a
`DISCRIMINATING_PROBE_PROPOSED`.

The proposed query has `reference_answer: UNOBSERVED`; its answer is never
fabricated from the competing hypotheses. If no in-regime probe separates
the remaining candidates, the result marks
`INSUFFICIENT_CURRENT_REGIME_DIVERGENCE` and requires a different
evidence regime. No candidate becomes a champion merely by winning a
training comparison. This is a bounded active-test mechanism, **not**
implementation of the canonical 15-cell D15/FFI investigator.

## Source-version lifecycle and replay (increment v0.2)

`rct_garden_lifecycle.py` now registers the bounded research experiment with
its exact training, evaluation, and revised-source SHA-256 identities in the
**existing append-only QualityRag research ledger**. Source identity here is
content fingerprinting, **not external source authenticity**.

`inspect_revisions` compares an observed source manifest against the
original experiment dependencies, including removed and unexpected sources.
`reopen_on_revision` emits a source-observation record followed by a new
`INCONCLUSIVE` assessment event if any bound source changes. Repeated
identical observations do not duplicate research events.

The retained event is an invalidation/replay **request**, not a replayed
experiment. The research cannot become `VALIDATED` or `ADMIT` from these
writes, and the original branch/events remain intact.

### Reproducible end-to-end local demonstration

```bash
python tools/semantic_store/rct_garden_lifecycle_demo.py \
  --db /tmp/garden-research.sqlite \
  --receipt /tmp/garden-experiment.json \
  --uri https://example.org/research/replace-with-real-receipt-uri
```

The demonstration uses *synthetic* data, persists a research experiment,
simulates a new source revision, **reruns the investigation**, and stores a
second claim with a `QUALIFIES` link to the earlier claim. The original
claim retains an append-only reopening event. The research assessment
remains `INCONCLUSIVE` for both versions. Its example URI does not
authenticate a document, and the separately written receipt file is not
automatically uploaded to that URI.

**Remaining limitation:** Existing research-ledger write functions commit
individual records; this adapter is not yet an atomic multi-write
transaction and can leave a partial local record on process interruption.
Only the canonical ledger backend should own transactional writes in a
production integration. The lifecycle is manually invoked and not
a continuously running scheduler.

### Replay semantics

`replay_after_revision` accepts actual source snapshots and new observation
references; it does not infer them from a screenshot or a GitHub commit. It
checks source identities against the original experiment, reruns bounded
training-only grammar induction, performs finite held-out evaluation on the
changed source, appends an invalidation event, and opens a **new** source-bound
experimental claim. `QUALIFIES` links the new claim to its historical
predecessor without asserting that either is a valid production champion.

Ambiguous or unresolvable re-induction leaves the old claim reopened and
returns a discriminating-probe request; it cannot fabricate research
evidence or promote an unverified operator.

Because research-ledger writes currently commit individually, the replay
operation is **not transactionally atomic** across every ledger record. A
process crash can leave incomplete local records; this must be resolved
through the canonical ledger transaction API before deployment.
