# Activation Constraints v0.1 — reproducible research slice

**Status:** executable finite declaration checker, **not** a generative codec, independently verified meaning-preservation engine, or live PackSpec admission.

## Where this fits the existing work

- Existing typed RCT grammar: `tools/semantic_store/rct_typed_grammar.py` implements bounded `EDGE/PATH/AND` structural induction.
- Existing PackSpec runtime: `tools/packspec_compiler/unified_gate.py` evaluates reviewed evidence requirements. This new module deliberately **does not** impersonate that gate.
- Existing governance bridge: `tools/semantic_store/rct_packspec_bridge.py` remains the fail-closed integration for approved, source-bound evidence requirements.
- New module: `tools/semantic_store/activation_constraints.py` tests **declared** candidate representation-preservation and activation budgets, with evidence status always `INCONCLUSIVE`.

## Core grammar

```text
ActivationGrammar ::= Regime+ Operator*
Operator ::= PRESERVE(fields)
           | TRANSITION(source_regime, target_regime)
           | ACTIVATE(regime, modules)
           | VERIFY(fields)
           | FALLBACK(regime)
```

In v0.1 these operators are *declarations*, not imperative operations. A `TRANSITION` is not yet executed, and an `ACTIVATE` does not load a model. No untrusted code is evaluated. Declarations are still checked: each operator may carry only its own keys (a misspelled key is rejected), and `PRESERVE`/`VERIFY` may only name fields the contract requires. They do not otherwise change the verdict, and observation *values* are checked for presence only, not compared.

## Run a real finite example

From the repository root:

```bash
PYTHONPATH=tools/semantic_store python - <<'PY'
import json
from activation_constraints import evaluate
with open("examples/activation-grammar/clinical.json") as f:
    case = json.load(f)
receipt = evaluate(case["grammar"], case["contract"], case["observations"],
                   max_activation_ms=5, max_model_bytes=500,
                   baseline_regime="raw")
print(json.dumps(receipt, indent=2))
PY
python -m unittest discover -s tools/semantic_store/tests -p 'test_activation_constraints.py' -v
```

Expected finite selected candidate: `clinical`; production `qualityrag_admission`: `INCONCLUSIVE`; `can_generate`: `false`.

Changing PackSpec-like constraints to require `exact_words` makes `clinical` infeasible and selects `raw` when that field's source observation is present. Removing the `context` observation produces `UNKNOWN`. The test suite exercises both.

## What is and is not measured

The reported `estimated_cost = payload_bytes + model_bytes` is **only a user-declared ranking proxy**, not measured file compression or lifecycle cost. `activation_ms` is a declared budget estimate. The model is treated as a standalone per-candidate cost, not amortized across viewers. It does not account for CPU/GPU energy, model downloads, updates, semantic reviewer costs, or SQL-equivalent capability.

Actual evaluator semantics:
- `SAT`: all *declared* required fields are claimed to be preserved; exact fields are claimed exact, source observation fields are present, and budgets are declared satisfied.
- `UNSAT`: at least one declaration visibly conflicts with the contract or budgets.
- `UNKNOWN`: required source observation or candidate preservation claim is missing.
- `INCONCLUSIVE`: **always** the QualityRag admission verdict, because there are no authenticated reviewers, independent witnesses or proven semantic equivalence.

A finite `SAT` never certifies a clinical diagnosis, a source observation, a lossless video decode, an independently approved PackSpec, or a trustworthy source.

## Next boundaries

1. Bind a source-authenticated reviewed PackSpec purpose and obligation IDs to the declared preservation field inventory; route evidence decisions through canonical `unified_gate.py`.
2. Execute meaningful typed `TRANSITION` and reversible `ACTIVATE` on independently checked finite data, with source/version receipts and explicit omission accounting.
3. Add costed compilation with measurable amortization and baseline equivalence; for video compare equal-quality AV1 and modern neural codecs.
4. Only introduce agent-generated candidates behind sandboxed evaluation, deterministic replay, counterexamples, and independent promotion review.
