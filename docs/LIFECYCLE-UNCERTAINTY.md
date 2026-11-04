# Lifecycle uncertainty and catalog scenarios

US-032 now supports deterministic cost ranges in addition to point scenarios.
These are models of supplied inputs, not measured savings, revenue forecasts,
statistical confidence intervals or proof of a compression advantage.

## Explicit cost inventory

Each cost group must declare all eleven components: compile, encode, residual,
model_distribution, update, storage, bandwidth, decode, verification, energy and
review. Each component has exactly lower, upper, evidence and unit.

| Property | Contract |
|---|---|
| lower / upper | Finite nonnegative JSON numbers, lower no greater than upper |
| evidence | OBSERVED, ASSUMED or UNKNOWN |
| unit | USD |
| UNKNOWN endpoints | Both null; missing cost is never silently zero |

lifecycle_interval reports a known subtotal range but leaves total_usd null
when any component is unknown. OBSERVED is a caller assertion about inputs, not
independent authentication. ASSUMED costs keep the result a scenario.

Catalog comparisons require six complete groups:

| Group | Multiplier |
|---|---|
| fixed | One per scenario |
| per_title | Declared catalog titles |
| per_install | Declared cohort installations |
| per_update | Declared cohort update events |
| baseline_per_view | Declared baseline views |
| candidate_per_view | Declared candidate views |

Declare all four cohorts: cold-new, frequent, smart-tv and mobile. Each supplies
installs, views and update_events. Counts are nonnegative signed-64-bit integers;
catalog sizes are positive, unique, and limited to sixteen scenarios. Zero costs
must be declared explicitly with an evidence class. A genuinely unknown
component makes the comparison inconclusive even if a supplied workload count
would currently multiply that scope by zero.

## Interpretation

The model holds installations, updates and catalog size fixed while varying
views to calculate crossover. It does not infer how these counts grow together.

Setup includes fixed, title, installation and update costs. Let setup range be
[Smin,Smax], baseline per-view costs [Bmin,Bmax] and candidate per-view costs
[Cmin,Cmax]. The marginal-saving range is [Bmin-Cmax,Bmax-Cmin].

- If even the best marginal saving is nonpositive, report NO_CROSSOVER.
- If the best marginal saving is positive, the earliest bound is
  floor(Smin / best_marginal) + 1.
- If the worst marginal saving is positive, the guaranteed-within-input-bounds
  threshold is floor(Smax / worst_marginal) + 1.
- If the worst marginal saving is nonpositive, no guaranteed threshold is
  reported, even if a best-case crossover is possible.

Equality is not savings. With setup USD 0.30 and per-view saving USD 0.10,
strict savings start at four views, not three. The code uses exact decimal
rational arithmetic internally and rounds displayed interval endpoints outward.
Overflow refuses rather than emitting infinite costs. Break-even thresholds are
mathematical model outputs and may exceed the supported input workload counts.

Bounds combine endpoints conservatively. Correlations are not modeled, so a
best-case endpoint combination may not be jointly attainable. Real outcomes
outside the supplied bounds are not covered. A guaranteed-within-input-bounds
result is not a financial guarantee.

At the declared view count, output distinguishes no savings within bounds,
uncertain savings, and positive savings throughout the supplied bounds.
economic_advantage remains NOT_ESTABLISHED and can_promote remains false.

## Run the model

The committed economic-scenario.json fixture is authored demonstration data:
all values, including explicit zeros, are ASSUMED. It is not Dodo LLC, LexyRead,
customer, cloud-provider or device measurement data.

~~~bash
python -m tools.activation_runtime.cli economics --request tools/activation_runtime/fixtures/economic-scenario.json
~~~

The request contains exactly groups, catalog_sizes and cohorts. Unknown options,
missing cost categories, duplicate catalog sizes and malformed counts refuse.
The same model is available through economics.catalog_uncertainty and
economics.lifecycle_interval.

## Promotion and investigation budgets

research_frontier compares bytes, latency, energy and total USD only for
fidelity-qualified, fully measured rows. Unknown energy/cost remains unqualified.
Duplicate IDs refuse, including IDs on unqualified rows. Declared finite values
are validated even on rows excluded for another reason. No frontier automatically
authorizes promotion.

The experiment scheduler uses exact decimal value/cost ratios and budget
subtraction, deterministic ID tie-breaking and unique bounded IDs. It remains a
greedy ranking heuristic, not a globally optimal knapsack solver or evidence
that expected values are accurate. Cost and value inputs are caller supplied.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_economic_uncertainty.py' -v
~~~

Tests cover possible/guaranteed/no crossover, unknown costs, all workload scopes,
strict equality boundaries, outward rounding, overflow, CLI parity, full Pareto
dimensions, duplicate IDs and exact scheduler budget/ranking behavior. Independent
catalog costs, actual energy use and economic outcomes remain acceptance gates.
