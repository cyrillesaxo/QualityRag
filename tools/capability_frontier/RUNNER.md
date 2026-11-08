# Capability Frontier v0.2 — Model Execution and Research Controls

## What is real

`runner.py` is an executable **synchronous model-run harness**, not a simulated
result table. It calls a supplied adapter for every case × trial × policy, and
passes completed raw runs to the existing `frontier.evaluate` evaluator.

`OpenAICompatibleAdapter` supports an **explicit, operator-controlled HTTPS**
chat-completions endpoint. It uses a key from the named environment variable,
does not provide external tools, and makes no background calls or retries.
No API credentials are stored in experiment manifests.

**No live LLM experiment was performed in this PR.** The deterministic fake
adapter is used only to test runner invariants.

## Execution contract

Inputs: `qualityrag.capability-runner/v0.1` manifest with a frozen `cases`
array (id, family, regime, development/holdout split, prompt, expected), positive
integer resource budgets, and optionally pre-reviewed experiment-only operator
cards.

Four policies are executed, paired by case, trial, model and configured tools:
baseline, tools, grammar and garden. The operator cards are **not executable**;
they are a frozen prompt-context intervention, and only cards explicitly marked
`REVIEWED_FOR_EXPERIMENT` are accepted. They cannot modify the PackSpec.

Gold `expected` and hidden case metadata are not supplied to the model adapter.
The runner does not protect against contaminated model training data or leaked
prompts elsewhere; genuinely hidden benchmarks require external custody.

`run_cli.py` uses a **provisional exact-match auditor**. This is adequate for
canonical short answers in development exercises but is not an independent
semantic proof, geometric point-incidence checker, or authenticated witness.

## Example

```json
{
  "schema": "qualityrag.capability-runner/v0.1",
  "budget": {
    "tokens_in": 8000, "tokens_out": 500, "tool_calls": 1,
    "wall_ms": 120000, "cost_microusd": 5000000
  },
  "cases": [
    {
      "id": "development-1", "family": "arithmetic", "regime": "integers",
      "split": "development", "prompt": "What is 7 times 8? Return only the integer.",
      "expected": "56"
    },
    {
      "id": "holdout-demo-1", "family": "arithmetic", "regime": "integers",
      "split": "holdout", "prompt": "What is 9 times 7? Return only the integer.",
      "expected": "63"
    }
  ]
}
```

This **illustrative** holdout is publicly described and cannot support
unseen-task capability claims.

```bash
export OPENAI_API_KEY=...
python tools/capability_frontier/run_cli.py \
  --manifest research-manifest.json \
  --output run-receipt.json \
  --endpoint https://YOUR-APPROVED-PROVIDER/v1/chat/completions \
  --model YOUR_APPROVED_MODEL \
  --input-price-microusd-per-million 1000000 \
  --output-price-microusd-per-million 2000000 \
  --trials 3
```

The sample rates are placeholders, **not verified provider pricing**.
For a true cost comparison, independently meter provider billing, wall
time, setup, verification, search and external tool costs. A provider may
reject `temperature: 0` or `max_tokens`; adjust the adapter and freeze that
configuration across arms before experimenting.

## Threats and scientific limits

1. The runner shares a model and no-tools fingerprint across conditions.
   The `tools` condition currently has **no tool invocation capability**.
   Therefore A-vs-B cannot establish tool augmentation effects.
2. It accepts usage metadata from the provider. This is not an independent
   financial or computational attestation.
3. Exact answer equality is inadequate for general natural language, source
   relevance, proofs or equivalence claims.
4. Operators are **human-pre-reviewed prompt cards**; the Garden does not
   autonomously invent, verify, or promote executable transformations here.
5. `max_output_tokens` is a request limit, not a guarantee. The harness
   rejects observed budget overruns, leaving an incomplete experiment.
6. The adapter runs locally with operator-supplied network access; it is not
   a security sandbox for adversarial code or untrusted plugins.
7. The existing RCT/PackSpec unified gate is untouched. Passing this
   benchmark does not meet k/b/c/τ, RCOC/HCR, FFI, FF-RCT, D15, CUS, WBC,
   WitnessGraph custody or TERM admission requirements.

## Research acceptance milestones

- **M1 — Baseline reproducibility:** execute authenticated, pinned models
  repeatedly with independent cost and oracle receipts.
- **M2 — Grammar ablation:** introduce typed operator proposals and track
  which exact operator/preservation obligation affected each result.
- **M3 — False-sibling controls:** 15 deceptive witness probes and regime-
  boundary negative transfer cases must be evaluated, not merely listed.
- **M4 — Genuine held-out frontier:** no known train/dev overlap, repeated
  unseen tasks, independent review and no unsupported baseline restrictions.
- **M5 — Semantic Garden loop:** discover mechanisms, generate operators,
  challenge across FF-RCT scales, verify with the canonical policy and
  store promoted reasoning kernels with TERM replay triggers.

## Reproduce CI checks

```bash
python -m unittest discover -s tools/capability_frontier/tests -p 'test_*.py' -v
```

This run is also defined as a dedicated PR-triggered GitHub Actions workflow.
