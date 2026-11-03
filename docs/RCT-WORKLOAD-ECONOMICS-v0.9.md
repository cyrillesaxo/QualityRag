# RCT Workload Economics v0.9

This experiment compares three *implementations* of the same finite, two-hop structural workload:

1. **Direct SQL join:** query the indexed original fact table without a derived index.
2. **SQL materialized relation:** build and index a precomputed two-hop relation, then query it.
3. **RCT candidate lens:** mine a composition operator from a separate training graph, verify the candidate on the supplied graph, materialize a dictionary projection, then query it.

**None is automatically superior.** The two SQL implementations are credible competing baselines. All semantic admission remains `INCONCLUSIVE`.

## Reproduce

From repository root:

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
PYTHONPATH=tools/semantic_store python - <<'PY'
from rct_benchmark import make_fixture, make_contract, run_benchmark, simulate_update
from json import dumps
train = make_fixture(entities=40, prefix="train-")
validation = make_fixture(entities=80, prefix="valid-")
contract = make_contract(validation, repetitions=12)
result = run_benchmark(validation, train, contract, trials=5)
print(dumps({"medians_ns":result["medians"],
             "same_answers":result["verified_identical_answers"],
             "scope":result["result_status"]}, indent=2))
print(dumps(simulate_update(validation,train,contract),indent=2))
PY
```

## Definition of work

- One declared workload: `two_hop_distinct_destinations`, with named predicates and source fingerprint.
- Repeated queries over each subject in the validation source, using exactly the same subject ordering and number of repetitions.
- The source load plus SQLite indexes is counted in all three total costs.
- SQL view build and index cost is counted in materialized SQL.
- Candidate discovery and finite-graph evaluation are counted in RCT lens build.
- Three or more trials are preferred; use median timings, not single noisy runs.
- Comparison is **only valid when every query yields the same answer**; mismatch raises an error.
- A changed source requires recompilation and renewed structural verification. The update test checks that invariant but does not time mutation overhead yet.
- The scope contract is experimental and intentionally NOT a PackSpec approval.

## Interpretation discipline

The result is a limited Python/SQLite wall-clock comparison, not an energy benchmark, byte-accurate memory measurement, causal demonstration of intelligence, or proof of novel operator invention. An in-memory Python lookup and SQLite SQL queries incur different language/runtime overheads. The supplied facts are synthetic and source authenticity is not established.

The work must be extended before any production performance claim: realistic distributions and query selectivity; source parsing; external authenticated PackSpec; sensitivity to workload size and update frequency; maintenance costs; RAM/disk accounting; FF-RCT encoding and reconstruction; and transfer across structurally different graphs.

**Acceptance rule:** A candidate lens is useful only when it preserves declared obligations and demonstrates lower *total* work than the best credible baseline for the target workload, or demonstrably enables a capability the baseline cannot support.
