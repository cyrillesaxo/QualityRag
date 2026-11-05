# Semantic Gardener in the QualityRag console

The Semantic Gardener is an append-only research tree. Branches are hypotheses, and every change is an event: `PROPOSE`, `CHALLENGE`, `TEST`, `SYNTHESIZE`, `PRUNE` or `REOPEN`. Nothing is ever deleted. A branch's evidence status comes from the research ledger, and nothing in the Gardener can mark a claim validated.

People use it in the console. Developers and AI agents use it through the SDKs, the CLI and an MCP server. All four call the same authenticated API, so a signed token's scopes decide what each caller may do.

| Scope | Allows |
|---|---|
| `read` | View the tree, query it, follow its growth, read suggestions |
| `write` | Also `PROPOSE`, `CHALLENGE` and `TEST` (with evidence already recorded in the ledger) |
| `review` | Also `PRUNE`, `REOPEN`, `SYNTHESIZE` and recording suggestion outcomes |

Give agents `read` + `write` tokens. The actor on every event is the token's subject, and the time is the server's clock; clients cannot set either.

## Console

Start the service and open it in a browser:

```bash
python -m tools.activation_runtime.cli serve --root ./workspace --keys keys.json --port 8769
# open http://127.0.0.1:8769 and paste a signed access token
```

The **Research tree** panel at the top of the workspace shows:

- **The tree.** It grows upward from root hypotheses as fractal limbs. Cyan means tested in the ledger, amber an open challenge, pale an unverified hypothesis, and dashed grey a pruned branch (still in history). A synthesis is drawn as two limbs merging.
- **Live growth.** New events from any person or agent appear within a few seconds; the panel polls the query API with `since`.
- **Query.** Free-text search over branch names and every event's statement, combined with filters: active, open challenges, tested, unverified. Non-matching branches dim.
- **Replay history.** A slider rebuilds the tree as it stood after any event.
- **Inspector.** Select a branch to see its statement, source, parents, events and, once reopened, the context restored with it. With write scope you can **Challenge**, **Test with evidence** or **Fork**; with review scope, **Prune** or **Reopen** through the existing review dialog.

## Query API

`POST /api/gardener/query` (read scope). Every field is optional, and filters combine with AND.

| Field | Meaning |
|---|---|
| `text` | Case-insensitive match on the branch name and all of its event statements (≤ 200 chars) |
| `evidence_status` | Ledger status, e.g. `UNVERIFIED`, `TESTED`, `VALIDATED`, `REFUTED` |
| `open_challenge` | `true`: a `CHALLENGE` not yet followed by a `TEST` |
| `active` | `false` for pruned branches |
| `lineage_of` | Keep this branch with its ancestors and descendants |
| `since` | Return the events appended after this sequence number |
| `limit` | 1–500 branches (default 200) |

The response lists branch summaries (statement, parents, children, status, open challenge, event count, source), the new events, and `head_sequence`. To watch growth, call it again with `since` set to the last `head_sequence`.

## AI agents (MCP)

`tools/activation_runtime/mcp_server.py` is a stdio MCP server with five Gardener tools (plus three read-only policy tools, see [GOVERNANCE-CONSOLE.md](GOVERNANCE-CONSOLE.md)):

- `garden_query`
- `garden_suggestions`
- `garden_propose`
- `garden_challenge`
- `garden_test`

Prune, reopen and synthesize are deliberately not exposed.

Example client configuration (Claude Code `.mcp.json`, or any MCP client):

```json
{
  "mcpServers": {
    "qualityrag-gardener": {
      "command": "python",
      "args": ["-m", "tools.activation_runtime.mcp_server"],
      "cwd": "/path/to/QualityRag",
      "env": {
        "QUALITYRAG_ENDPOINT": "http://127.0.0.1:8769",
        "QUALITYRAG_TOKEN_FILE": "/path/to/agent-token.json"
      }
    }
  }
}
```

Every write tool needs a source. Pass `source_text` (stored and hashed in the workspace) or `source_sha256`. For challenges, tests and forks, leave both out to reuse the branch's own source.

## Python, TypeScript and CLI

```python
from qualityrag_activation import Client
garden = Client("http://127.0.0.1:8769", token)
garden.garden_query(text="labeler", open_challenge=True)
source = garden.upload(b"Experiment notes")["source_sha256"]
garden.garden_event(event_id="exp-42", operation="CHALLENGE", branch="llm-labeler",
                    source_sha256=source, source_ref="notes#3", statement="Self-abstaining LLMs may match it")
```

```ts
const garden = new ActivationClient('http://127.0.0.1:8769', token);
const { branches, head_sequence } = await garden.gardenQuery({ text: 'labeler' });
const growth = await garden.gardenQuery({ since: head_sequence });
```

```bash
python -m tools.activation_runtime.cli garden query --endpoint http://127.0.0.1:8769 --token agent.json --open-challenge
python -m tools.activation_runtime.cli garden watch --endpoint http://127.0.0.1:8769 --token agent.json   # JSON line per new event
```

## Limits

- Suggestions find exact-statement duplicates and unresolved challenges only. Paraphrase and contradiction detection need a semantic labeler and are not built yet.
- Replay rebuilds structure (branches, prunes, challenges) at any moment, but evidence status is shown as it is now. The ledger is not replayed.
- Every append replays the whole chain, and suggestions scan at most 2,000 events. That is fine for a project, not yet for years of history.
- Live growth polls every 4 seconds; there is no push channel.

## Governance tools

The same console has a **Governance** panel with a policy tester, an advisor and policy-branch replay. Open Gardener challenges appear as Advisor findings. See [GOVERNANCE-CONSOLE.md](GOVERNANCE-CONSOLE.md).
