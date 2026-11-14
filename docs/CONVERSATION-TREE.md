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

## Run

```bash
python -m unittest discover -s tools/conversation_tree/tests -p 'test_*.py' -v
python -m tools.conversation_tree.demo
```

## Boundaries

- **Obligations are candidates.** `triggers.py` is a versioned English lexical inventory (exceptions,
  negations, conditions, deadlines, numbers, modality, back-references, supersession). A constraint with
  no marker is missed. Recall is unmeasured.
- **The classifier is unmeasured.** Only explicit markers produce `REFINE` or `PIVOT`; everything else
  forks. It has not been scored against human labels.
- **Only USER turns bind.** Assistant, tool and system text cannot govern, confirm, supersede or witness.
  Operator and user-level rules above the root are not modeled yet.
- **Scope of the gate.** It checks whether the turns behind critical candidates are loaded. It does not
  check that a model used them, and an empty inventory stays `INCONCLUSIVE`.
- **Separate chain.** The event chain follows the Gardener pattern but does not write to the Gardener or
  the Research Ledger. See open decision 1 in the epic.
- **Trust boundary.** Hash chains and triggers detect ordinary corruption; they do not stop a database
  administrator.

No lake, retrieval API, MCP tool, differential branch test or evaluation exists yet.
