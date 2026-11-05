# Semantic Garden Capability Frontier — Research Contract v0.1

This is an **offline evaluation harness**; it neither runs LLMs nor claims that new capabilities have been demonstrated. Its purpose is to measure whether the *same* agent runtime, under a frozen tool configuration and equal constraints, reliably solves previously unsolved held-out regimes when supplied with additional semantic grammar or evolving Garden operators.

## Predeclared policies

- **baseline** — LLM agent operating normally
- **tools** — same model with conventional tools and retrieval
- **grammar** — same runtime with a frozen typed grammar / RCT strategy
- **garden** — same runtime plus proposed, previously evaluated reusable operators

All policies must be paired by case, trial, model ID, tool fingerprint, and per-run budget. Holdout family boundaries must be frozen before any training or operator selection.

## Input format

`cases.json` is an array of records containing `id`, `family`, `regime`, `split` (`development` or `holdout`) and a canonical `expected` answer. Never expose `expected` to the candidate agent.

`budget.json` contains nonnegative per-run integer caps: `tokens_in`, `tokens_out`, `tool_calls`, `wall_ms`, `cost_microusd`.

`runs.json` is an array of records, one per case × trial × policy. Each row must contain `case_id`, `trial`, `policy`, `model_id`, `tools_fingerprint`, `output`, `tokens_in`, `tokens_out`, `tool_calls`, `wall_ms`, `cost_microusd`, `constraint_violations` and `auditor_ref`.

**Important:** This code checks measurement structure but cannot verify that the external meter or auditor are honest. A trusted harness, not the evaluated agent, must supply measured costs, truth checks, and constraint violations. Exact-match oracles are insufficient for unconstrained language answers; integrate independently verified semantic/proof checkers for those.

## Run

```sh
python tools/capability_frontier/cli.py --cases cases.json --runs runs.json --budget budget.json --output receipt.json
python -m unittest discover -s tools/capability_frontier/tests -v
```

The receipt reports per-case success rates and cost, held-out frontier gains, regressions, and input SHA-256 digests. It does not claim causal attribution or intrinsic model enhancement.

## Admission and lifecycle

`assess_operator` produces **CANDIDATE** only. No automated promotion is possible in this module. Operators must satisfy the existing PackSpec/ConstraintIR authority and real FF-RCT, FFI, HCR/RCOC, 12G, k/b/c/τ, WitnessGraph, WBC, CUS, TERM and applicable D15 probes before an authorized reviewer can approve promotion.

Reject or reopen any result using a reused/contaminated holdout, hidden model advantage, uncertified oracle, unmeasured setup or verification costs, unsupported semantic equivalence, altered required constraints, deceptive independent witnesses or expired source authority.

## Next phases

1. A trusted agent execution and meter adapter for actual models and tool calls.
2. Independent canonical answer-oracles and case manifests including contamination controls.
3. Bidirectional RCOC/HCR and Functional Sibling operator proposal traces.
4. D15 adversarial probes, provenance-aware WitnessGraph receipts, TERM replay, and admission gates.
5. Repeated experiments over multiple models and genuinely unseen families, including negative transfer.

The present scope is the **instrumentation needed to distinguish capability-frontier expansion from search optimization**.
