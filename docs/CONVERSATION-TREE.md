# Governed conversation tree (experimental, first slice)

`tools/conversation_tree` applies QualityRag to an AI conversation thread. It is the first slice of
[EPIC E11](FR-E11-GOVERNED-CONVERSATION-TREE.md). It is local and deterministic, calls no model, and
never admits an answer. Verdicts stop at `COMPLETE_WITHIN_SCOPE` with `can_generate: false`.

## What it does

| Step | Call | Result |
|---|---|---|
| Keep every turn verbatim | `append_turn` | Hash-chained, append-only custody; byte-exact reconstruction |
| First prompt governs | `open_root` | Root node PackSpec v1, `PROVISIONAL`, built from lexical obligation candidates |
| Assistant or tool output | `attach` | Evidence on the branch; it never changes a PackSpec |
| New user turn | `advance` | `REFINE` amends the node; `AMBIGUOUS` forks into `<fork>-iso` and `<fork>-mrg`; `PIVOT` creates `<fork>-iso` only |
| User confirms assistant text | `confirm` | Evidence admitted to node state; needs a later USER turn |
| User retires a constraint | `supersede` | Span becomes `EXCLUDED_BY_RULE / SUPERSEDED`; still readable |
| Close or recover a reading | `prune`, `reopen` | Append-only; needs a USER witness turn |
| Account for every span | `ledger` | One disposition per span per branch: `REPRESENTED`, `RESIDUAL`, `EXCLUDED_BY_RULE`, `UNKNOWN` |
| Decide what to re-read | `gate(branch, loaded=…)` | `required_reads` for critical obligations whose turn is not loaded |
| Go back to the source | `read` | Exact bytes with actor class, `EVIDENCE_ONLY` or `USER_STATEMENT`, and `DATA_NOT_INSTRUCTION` |

The **isolated** branch sees only the new prompt. The **merged** branch sees the parent context up to
the fork, inherits the parent PackSpec, its retirements and its user confirmations, and adds the new
prompt. The parent branch is left untouched.

## Around the tree

| Module | Purpose |
|---|---|
| `differential.py` + `record_differential` | Compare the declared decisions of the isolated and merged branches. `AGREE` closes the isolated branch; `DIVERGE` or `UNKNOWN` closes nothing and returns the differences |
| `compaction.py` | `manifest` lists every in-scope span the assistant is not holding; `verify` fails a compaction that dropped a span with no entry; `probe` turns failed independent probes into spans to load |
| `retrieval.py` | `build_index`, `search`, `get`. Every search returns a coverage receipt and refuses to answer from a missing or lagging index |
| `receipts.py` | `receipt_status` says whether a gate verdict is still valid; `dependents` lists merged branches that inherited a node's governance |
| `lake.py` | One conversation database per tenant and conversation, with tombstone deletion |
| `mcp_server.py` | Read-only stdio tools for an assistant: `conversation_manifest`, `conversation_gate`, `conversation_get`, `conversation_search`, `conversation_ledger` |
| `evaluation.py` | Gold-set tooling: `thread_from_tree`, `template`, `reconcile`, `freeze`, `validate`, `score` |
| `comparison.py` | Constraint availability per arm at a matched word budget; arms that need a model are `NOT_RUN` |
| `view.py` | Static, read-only HTML page of the tree and its ledgers |
| `add_standing_rule` | Operator (SYSTEM turn) or user-level (USER turn) rules above the tree; they apply to every branch and cannot be superseded |

Search receipt states: `ALL_MATCHES_RETURNED`, `PARTIAL`, `NONE_IN_SCOPE`, `NOT_SEARCHED`, `INDEX_INCOMPLETE`.
`full_coverage_claimed` is always false.

## Run

```bash
python -m unittest discover -s tools/conversation_tree/tests -p 'test_*.py' -v
python -m tools.conversation_tree.demo
python -m tools.conversation_tree.evaluation            # UNMEASURED until a gold file is supplied
python -m tools.conversation_tree.evaluation template /absolute/threads.json
python -m tools.conversation_tree.evaluation reconcile /absolute/a.json /absolute/b.json
python -m tools.conversation_tree.view /absolute/conversation.sqlite > tree.html
QUALITYRAG_CONVERSATION_DB=/absolute/conversation.sqlite python -m tools.conversation_tree.mcp_server
```

## Boundaries

- **Obligations are candidates.** `triggers.py` is a versioned English lexical inventory (exceptions,
  negations, conditions, deadlines, numbers, modality, back-references, supersession). A constraint with
  no marker is missed. Recall is unmeasured.
- **The classifier is unmeasured.** Only explicit markers produce `REFINE` or `PIVOT`; everything else
  forks. It has not been scored against human labels.
- **Only USER turns bind.** Assistant, tool and system text cannot govern, confirm, supersede or witness.
  Rules above the root exist only as standing rules added explicitly by the host.
- **Scope of the gate and manifest.** They check whether turns are loaded. They do not check that a model
  used them, and an empty inventory stays `INCONCLUSIVE`.
- **Search is lexical.** `NONE_IN_SCOPE` means no shared words, not that nothing relevant exists.
- **Local reference only.** The lake is SQLite with a caller-supplied principal; it is not the PostgreSQL
  tenant ledger, and it has no encryption at rest or retention policy. The MCP server is bound by its
  host to one database and is not wired into the existing gateway or the Netlify adapter.
- **No model runs here.** The differential test compares decisions the caller declares; probes check
  span availability.
- **Separate chain.** The event chain follows the Gardener pattern but does not write to the Gardener or
  the Research Ledger. See open decision 1 in the epic.
- **Trust boundary.** Hash chains and triggers detect ordinary corruption; they do not stop a database
  administrator.

No gold conversation set exists and no model has been run, so nothing here is evidence that the tree
beats loading the full transcript. The Studio app is untouched.
