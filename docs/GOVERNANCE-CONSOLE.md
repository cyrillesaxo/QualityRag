# Policy tester, Advisor, branch replay and functional siblings

The QualityRag console has four Evidence screens: **Check an answer** (policy tester), **Health** (advisor), **Policy changes** (branch replay) and **Alternatives** (functional siblings). They sit on the v0.1 deterministic gate (`qualityrag.compiler.evaluate_compiled`). None of them changes a verdict, the ledger or the Gardener. `ADMIT` remains metadata gate satisfaction, not authorization to act.

All four need only `read` scope. People use them in the console. Developers and agents use the same API through the Python and TypeScript SDKs and the MCP server.

## Using the console without the internals

- **Sample data by default.** Every screen opens with something to run. Check an answer, Policy changes and Alternatives load the EU payments or joining sample themselves; **Use my own documents** swaps in your file.
- **Forms, not JSON.**
  - Passages are a checklist.
  - A policy is a list of requirements, each with *Independent sources* and *Max age (days)* fields.
  - Policy changes start from a suggested stricter version of the current policy.
  - The PackSpec JSON, recorded cases and requirement sets stay under **Advanced**.
- **Plain language first, the exact term beside it.**
  - Check results: *Supported*, *Not enough evidence* or *Contradicted*, with the gate verdict (ADMIT, INCONCLUSIVE, REFUSE) as a tag.
  - Health severities: *Must fix*, *Review* and *Good to know*.
  - Alternatives: *Works*, *Fails* or *Unknown*.
- **Background checks.** Health checks run when you sign in and after each check. Home and the sidebar badge show what needs attention.
- **Light or dark.** The top bar has a System / Light / Dark switch. System follows the operating system, and a choice is remembered in this browser. The research tree keeps its dark panel in both themes.
- **Connect.** Copy-ready curl, Python, TypeScript, CLI and MCP setup for the same API, with the console's own endpoint filled in.

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

## Functional siblings

This tab implements the relations proposed in *Functional-Sibling Discovery and Regime Convergence* (working paper v4, 5 Nov 2026), §2.1, §2.2 and §5, on top of the gate:

| Relation | Computed as |
|---|---|
| Feasible(s, F, C) | The gate's verdict on candidate s's evidence against contract C: SAT (ADMIT), UNSAT (REFUSE: contradicting evidence) or UNKNOWN (INCONCLUSIVE), never a forced binary |
| FunctionalSibling(a, b \| F, C) | a and b both SAT under C |
| D(F, C) | The SAT subset of the candidates supplied: a discovered set, not the complete one |
| Regime boundary | A candidate whose status changes between two contracts, with the requirements that decided it |
| Probe | An UNKNOWN requirement: the evidence to collect next |

For a function and a set of named contracts (PackSpecs), it returns:

- the candidate × contract matrix;
- sibling groups per contract;
- every regime boundary;
- the probe list;
- a coverage statement.

Siblinghood is relative to its contract and never equivalence, so nothing is merged. Copies still count as one origin, so two copies of one source do not make a candidate SAT under a two-origin contract.

**Load joining example (paper §4)** restates the paper's thought experiment as data: seven fasteners, and the contracts "join" and "join and separate repeatedly without damage". All seven are siblings under "join". Under the separation contract, only the rivet is UNSAT, because the paper contradicts it explicitly. The other six stay UNKNOWN: the paper says many adhesives and welds fail, but not all, and gives no positive evidence for the rest. Those six are the probes. The example is illustrative, not measured: every evidence row cites the paper and shares one origin.

`POST /api/policy/siblings` takes `function`, `contracts` (name → PackSpec), `candidates` (each `{id, evidence: [witness rows], label?, mechanism_family?, branch?}`) and optional `as_of`.

## Re-checking after a witness changes

`gardener/query` takes `depends_on`: an evidence ID or a source SHA-256. It returns the branches whose events cite it, marked `direct`, and every descendant, marked `inherited`. That is the set to re-check when the witness changes, and nothing else. The same filter is available in the CLI (`garden query --depends-on`), the SDKs and the MCP tool `garden_query`.

## From code

```python
from qualityrag_activation import Client
qr = Client("http://127.0.0.1:8769", token)
ex = qr.policy_example()
test = qr.policy_test(pack=ex["pack"], documents=ex["documents"], retrieved=ex["retrieved"])
advice = qr.policy_advise(pack=ex["pack"], test=test)
diff = qr.policy_replay(base=ex["pack"], branch=ex["branch_pack"], cases=ex["cases"])
sib = ex["siblings_example"]
siblings = qr.policy_siblings(function=sib["function"], contracts=sib["contracts"], candidates=sib["candidates"])
stale = qr.garden_query(depends_on="squad-run-1")   # branches to re-check
```

```ts
const qr = new ActivationClient('http://127.0.0.1:8769', token);
const test = await qr.policyTest({ pack, documents, retrieved });
const advice = await qr.policyAdvise({ pack, test });
```

The MCP server (`tools/activation_runtime/mcp_server.py`) exposes them as the read-only tools `policy_test`, `policy_advise`, `policy_replay` and `functional_siblings`, beside the Gardener tools. An agent can test a pack, read the findings and replay a stricter branch before it proposes the change in the Gardener.

## Limits

- **Labeling.** The tester uses the status already recorded on each chunk. Re-labeling with the lexical or LLM labeler, and replaying a labeler threshold, happen in the SQuAD benchmark on PR #71, not in the console.
- **Qualifiers.** Detection is a fixed word list. It flags spans for a person to read and does not decide what a condition means.
- **Replay.** It re-evaluates recorded evidence only; it does not re-run retrieval.
- **Promotion.** Signed three-role promotion of a policy branch is designed (see the QualityRag Console canvas) but not built. The console says so.
- **Functional siblings.** Candidates and their evidence are supplied, not generated. The thesaurus-grammar traversal that proposes candidates (paper §3), and the B1–B5 ablation experiment (§8.2), are not built. A boundary shows where status changes for these candidates; it is not evidence of a hidden cause (§5.1).
- **Request size.** Requests are capped at 512 KB. Larger corpora go through the SDK in batches.
