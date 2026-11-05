# Policy tester, Advisor and branch replay

The **Governance** panel in the QualityRag console has three tools that sit on the v0.1 deterministic gate (`qualityrag.compiler.evaluate_compiled`). None of them changes a verdict, the ledger or the Gardener. `ADMIT` remains metadata gate satisfaction, not authorization to act.

All three need only `read` scope. People use them in the console. Developers and agents use the same API through the Python and TypeScript SDKs and the MCP server.

## Policy tester

Run the gate on retrieved chunks and see exactly what it counted.

- **Verdict** for the pack, with the number of requirements admitted, admitted with a qualifier, admitted on a single origin, and retrieved chunks that were not counted.
- **Per requirement:** required versus actual distinct origins, and every linked span with its document, origin, format, revision and section.
- **Per span:** whether it added an origin. Each span is evaluated alone through the gate, so this is the gate's own answer, including age, scope and authority rejections. Copies of one origin are marked "counted once". Qualifier words inside supporting spans are highlighted, because the gate counts the span without evaluating them:
  - conditions: unless, except, excluding, provided that, subject to, conditional on, if and only if, only if, as long as
  - limits: only
  - negation: not, never, no longer, without
- **Retrieved, not counted:** chunks with no requirement link or status.

**Load EU payments example** loads `examples/enterprise-rag/corpus.json`. On it the gate returns ADMIT, while the tester shows that:

- `ops-7.3` and `ops-mirror-7.3` collapse to one origin, `ops-handbook`;
- `annex-d-187` is admitted despite "unless";
- `memo-exception` is admitted despite "only".

`POST /api/policy/test` takes `pack`, `documents` (each with `id`, `origin` and `chunks` of `id`, `text`, `requirement_id`, `status`), `retrieved` (chunk IDs in order), and optional `question` and `as_of`.

## Advisor

The Advisor reports what the gate does not check. Findings are sorted ERROR, WARN, INFO; any ERROR blocks promotion of a policy branch.

| Finding | Severity | Checks |
|---|---|---|
| `trust.no-active-reviewer` | ERROR | `reviewer-trust.json` has no active key, so signed completion receipts cannot verify |
| `trust.compromised` | WARN | Compromised keys are still listed |
| `trust.unreadable` | ERROR | The trust store does not load |
| `calibration.false-admission` | ERROR | A benchmark report's false-admission rate is above the limit (default 10%) |
| `evidence.qualified-support` | WARN | Admitted supporting spans contain qualifiers (needs a policy-test result) |
| `pack.single-origin` | WARN | Requirements with `min_independent_sources: 1`, and the copies that collapsed in the last test |
| `pack.no-max-age` | INFO | Requirements without `max_age_seconds` |
| `gardener.open-challenge.<branch>` | INFO | Active Gardener branches whose last challenge has no TEST after it |

Every finding gives what was checked, the fix, and a command or PackSpec snippet. In the console it uses the pack and result from the last policy test. A benchmark report is any JSON with `false_admission_rate`, `answer_rate` and `n`, plus optional `labeler` and `dataset`. The SQuAD 2.0 benchmark on PR #71 produces these figures.

`POST /api/policy/advise` takes optional `pack`, `test`, `benchmark` and `far_limit`. The server adds the trust store and the tenant's Gardener state.

## Branch replay

Re-evaluate recorded cases under the current pack and a branch pack, and see every verdict that changes.

- **Policy diff:** requirement fields added, removed or changed.
- **Counts:** admitted before and after, and verdicts changed.
- **With `expect_admit` labels:** false admissions removed, correct answers lost, and the false-admission and answer rates before and after.
- **Flips table:** every changed case and its effect.

The example branch raises `recovery-procedure` to two origins. The fully retrieved case flips from ADMIT to INCONCLUSIVE. Its cases are unlabeled, so no rates are shown.

`POST /api/policy/replay` takes `base`, `branch`, `cases` (each `{id, evidence: [witness rows], expect_admit?, question?}`, up to 5,000), and optional `as_of`.

## From code

```python
from qualityrag_activation import Client
qr = Client("http://127.0.0.1:8769", token)
ex = qr.policy_example()
test = qr.policy_test(pack=ex["pack"], documents=ex["documents"], retrieved=ex["retrieved"])
advice = qr.policy_advise(pack=ex["pack"], test=test)
diff = qr.policy_replay(base=ex["pack"], branch=ex["branch_pack"], cases=ex["cases"])
```

```ts
const qr = new ActivationClient('http://127.0.0.1:8769', token);
const test = await qr.policyTest({ pack, documents, retrieved });
const advice = await qr.policyAdvise({ pack, test });
```

The MCP server (`tools/activation_runtime/mcp_server.py`) exposes them as the read-only tools `policy_test`, `policy_advise` and `policy_replay`, beside the Gardener tools. An agent can test a pack, read the findings and replay a stricter branch before it proposes the change in the Gardener.

## Limits

- **Labeling.** The tester uses the status already recorded on each chunk. Re-labeling with the lexical or LLM labeler, and replaying a labeler threshold, happen in the SQuAD benchmark on PR #71, not in the console.
- **Qualifiers.** Detection is a fixed word list. It flags spans for a person to read and does not decide what a condition means.
- **Replay.** It re-evaluates recorded evidence only; it does not re-run retrieval.
- **Promotion.** Signed three-role promotion of a policy branch is designed (see the QualityRag Console canvas) but not built. The console says so.
- **Request size.** Requests are capped at 512 KB. Larger corpora go through the SDK in batches.
