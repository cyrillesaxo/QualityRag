# EPIC E11 — Governed conversation tree, conversation lake and completeness-backed read-back

> **Backlog addendum to [FR.MD](../FR.MD)** · **Drafted:** 2026-11-14 · **Owner:** APX / QualityRag research program
> **Status:** Stories are **PLANNED** unless listed under *Implementation evidence — first slice* below. No story here is DONE.
> **Scanned against:** `main` at `188ba89` (2026-11-13).
> **Story IDs:** US-069 to US-086. US-052 to US-065 are unused, but US-066 and US-068 already exist in `docs/`, so this epic starts after them to avoid collisions.
> **Why a separate file:** `tools/activation_runtime/audit.py` requires the story set in FR.MD to be exactly US-001 to US-051 and to match `capabilities.json`. These stories are therefore not yet in the audited inventory; registering them means changing that audit deliberately.

## Purpose

Apply QualityRag to an AI conversation thread. The thread becomes a tree in which every branch is a node governed by a PackSpec. The first prompt is the provisional governance. When a later prompt drifts, the system forks instead of guessing: one branch takes the new prompt in isolation, the other merges the governance, the assistant's response and the new prompt. Everything is kept in a tenant-scoped lake, and a completeness ledger tells the assistant what exists outside its loaded context so it can go back and read it.

**Falsifiable claim:** at matched token cost, a governed tree with a conservation ledger and ledger-triggered read-back produces fewer stale-constraint violations and fewer dropped constraints than summary compaction. Loading the full transcript into context is the comparator to beat (US-085). A negative result is retained.

**Scope boundary (invariant 8):** this is a conversation-memory regime. It shares interfaces with the document and video regimes but none of their fidelity guarantees.

## What already exists and must be reused

| Existing anchor | Story | Use in E11 |
|---|---|---|
| `tools/activation_runtime/gardener.py` append-only event chain, `PROPOSE/CHALLENGE/TEST/SYNTHESIZE/PRUNE/REOPEN` | US-034, US-035 | The pattern for the tree store: hash-chained, append-only, replayed. Collapse is `PRUNE`; recovery is `REOPEN`. See open decision 1 for why the first slice uses a separate chain. |
| `gardener.query(depends_on=…)` | US-034 | Dependency frontier for revalidation (US-083). |
| `tools/semantic_store/rct_source_span_conservation.py` | US-008 | Offset and hash checking for the turn-span ledger (US-076). Its inventory is caller-supplied today; US-077 supplies a non-circular generator. |
| Source custody and signed omission review | US-017, US-006/008 | Verbatim turn custody (US-069) and user-attributed locks (US-086). |
| `apps/registry/src/pg-store.js`, `pg-private-retrieval.js`, tenant ledger | US-043 | Lake storage and tenant isolation (US-080). |
| `apps/registry/src/governed-retrieval.js` | — | Retrieval seam that the coverage receipt extends (US-081). |
| `tools/activation_runtime/mcp_server.py`, `netlify/mcp` | — | Read-back tools for assistants (US-082). |
| `tools/research_ledger` | US-036 | Evidence status. No conversation node is ever VALIDATED by the tree itself. |

## Added invariants for this epic

9. **Assistant output is evidence, never governance.** Only a user turn, or a rule above the conversation, can bind.
10. **Fork on doubt.** An uncertain drift classification forks; it never silently refines or silently pivots.
11. **Two ledgers.** Turn-span conservation and obligation status are separate. Neither can stand in for the other, and storing everything as residual earns no coverage credit.
12. **Scoped verdicts only.** The strongest verdict is `COMPLETE_WITHIN_SCOPE`, carrying the snapshot, branch, PackSpec version and trigger-set version. It is never an `ADMIT` by itself.
13. **Stored content is data.** Text returned from the lake carries its actor class and authority and is never executed as an instruction.

## User stories and acceptance criteria

### A. Tree and governance

**US-069 · P0 · Verbatim turn custody (conversation universe)**
As an auditor, I want every user, assistant and tool turn stored immutably so the conversation can always be reconstructed exactly.
**Acceptance:** (1) Each turn stores bytes, SHA-256, actor class (`USER`, `ASSISTANT`, `TOOL`, `SYSTEM`), sequence and timezone-aware timestamp, reusing US-017 custody. (2) Reconstructing the conversation from the store is byte-identical under randomized property tests, including Unicode, empty turns and attachments by reference. (3) A missing, reordered or altered turn fails the round trip and is reported as a fidelity limitation, not repaired. (4) Verbatim storage is explicitly reported as zero semantic coverage.

**US-070 · P0 · Node PackSpec and provisional root governance**
As a user, I want my first prompt treated as the governing contract of the conversation, and I want to be able to amend it.
**Acceptance:** (1) The first user turn compiles to a root node PackSpec at version 1, marked `PROVISIONAL`. (2) Every node has exactly one governing PackSpec version; an amending user turn creates a new version and the old one is retained and addressable. (3) A user can explicitly promote any node to governance or demote the root; both are append-only, attributed events. (4) Operator and user-level rules sit above the root and cannot be overridden by any node. (5) A first prompt with no extractable obligations yields an empty PackSpec plus an `UNKNOWN` marker, never an invented one.

**US-071 · P0 · Actor-class authority in node admission**
As a security engineer, I want assistant and tool output prevented from becoming governance, so a model cannot bind the user with its own earlier text.
**Acceptance:** (1) `ASSISTANT` and `TOOL` spans enter a node only as evidence. (2) An assistant-proposed decision is admitted to node state only when a later user turn confirms or builds on it, with anchors to both turns. (3) Conflict order is fixed: newer user statement, then older user statement; assistant text never wins. (4) Instruction-like text inside stored assistant, tool or attachment content does not change governance in tests, including an injected "ignore the earlier rules" fixture. (5) Admission of assistant content without a confirming user anchor refuses.

**US-072 · P0 · Three-way turn classification with fail-to-fork**
As a conversation engine developer, I want each new user turn classified as a refinement, an ambiguous drift or a clear pivot.
**Acceptance:** (1) Output is one of `REFINE`, `AMBIGUOUS`, `PIVOT`, with the features that produced it. (2) Deterministic features (explicit references to earlier turns, supersession markers, shared defined terms) are evaluated before any model judgment. (3) Low confidence, budget exhaustion or classifier error returns `AMBIGUOUS`. (4) Accuracy is measured against the frozen human-labelled set from US-084, with the full confusion matrix reported; the classifier never grades itself. (5) Classifier version and thresholds are recorded on every event.

**US-073 · P0 · Drift fork into isolated and merged branches**
As a user, I want an ambiguous follow-up to produce both readings instead of a guess.
**Acceptance:** (1) `AMBIGUOUS` appends one fork event and two sibling branches on the existing Gardener chain. (2) The **isolated** branch contains the new prompt plus user-level rules only. (3) The **merged** branch contains the governing PackSpec, the admitted node state, the assistant's response as evidence under US-071, and the new prompt. (4) `REFINE` amends the current node without forking; `PIVOT` creates the isolated branch only. (5) Both branches record the fork event ID, parent node and PackSpec versions; replay after restart rebuilds the same tree with no cycles.

**US-074 · P1 · Differential branch test**
As a product owner, I want the two branches compared so the fork is only surfaced when earlier context changes the answer.
**Acceptance:** (1) Both branches run with the same model version and budget. (2) Comparison is at the level of declared obligations and decisions through a stated comparator, not string equality. (3) `AGREE` collapses the fork without interrupting the user and records that the earlier context was not load-bearing. (4) `DIVERGE` surfaces the difference or asks the user; a comparator that cannot decide returns `UNKNOWN`, which is handled as `DIVERGE`. (5) The comparator is not the classifier under test, and the added cost per fork is recorded as OBSERVED.

**US-075 · P1 · Witnessed collapse, reopen and branch budget**
As a user, I want the reading I did not mean retired without being lost, and I do not want the tree to double forever.
**Acceptance:** (1) A later user turn that discriminates between siblings is recorded as the witness for the surviving branch. (2) The other branch is closed with the existing `PRUNE` operation, with the witness turn ID and reason; nothing is deleted. (3) `REOPEN` restores the branch with its prior context and challenges. (4) A configurable cap on live branches per conversation is enforced; at the cap the engine asks the user to choose and never drops a branch silently. (5) Branch count, churn, collapse latency and reopen rate are reported.

### B. Conservation ledger and completeness

**US-076 · P0 · Turn-span conservation ledger (conversation DiffPackSpec)**
As a reviewer, I want every span of every turn accounted for against each active branch, so nothing leaves the working state unnoticed.
**Acceptance:** (1) For each active branch, every span in the universe has exactly one disposition: `REPRESENTED`, `RESIDUAL`, `EXCLUDED_BY_RULE` or `UNKNOWN`. (2) Each exclusion cites its rule: superseded by a named version, out of scope by a named fork event, or a declared non-content rule. (3) Gaps, overlaps, invented offsets and stale turn hashes fail, reusing the span checks in `rct_source_span_conservation.py`. (4) Obligation status is kept in a separate ledger with `SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`, `NOT_APPLICABLE` and `UNKNOWN`. (5) A branch whose spans are all `RESIDUAL` is valid and reports zero admitted coverage; this is the degenerate baseline in US-085.

**US-077 · P0 · Extractor-independent obligation triggers**
As a scientific reviewer, I want candidate obligations generated without the extractor being judged, so the denominator is not circular.
**Acceptance:** (1) A versioned, deterministic trigger inventory marks spans containing exceptions, negations, conditions, deadlines, numbers and units, modal verbs, references to earlier turns, and supersession markers, with no model call. (2) Every triggered span must receive a disposition and, where it states a constraint, an obligation entry. (3) Trigger recall and false-trigger rate are measured against the US-084 gold set and reported per trigger family. (4) The inventory is declared incomplete by construction: constraints with no lexical marker are counted as misses, not assumed absent. (5) A changed trigger-set version invalidates dependent verdicts.

**US-078 · P1 · Context compaction with a residual manifest**
As an assistant runtime, I want compaction to tell me what it left out, so I know something exists even when I am not holding it.
**Acceptance:** (1) Every compaction emits a manifest listing each unloaded node or span with ID, type, criticality, disposition and a bounded one-line stub. (2) A compaction that drops a span with no manifest entry fails. (3) Manifest size is bounded and the bound is tested. (4) Independently sourced probe questions are answered from the compiled state alone; a failed probe promotes the span to loaded or marks it critical `RESIDUAL`. (5) Probes are not produced by the model and prompt that performed the compaction.

**US-079 · P0 · Decision-scoped read-back gate**
As a user, I want the assistant to go back and read what matters before it answers, or to say that it could not.
**Acceptance:** (1) Before an answer on a branch, the obligations in scope for that decision are evaluated from the ledger. (2) Any critical obligation that is `UNSUPPORTED`, `UNKNOWN` or backed only by a `RESIDUAL` span forces a dereference by ID or returns `INCONCLUSIVE` with the unresolved list. (3) The trigger is the ledger, not model discretion; a test proves the gate fires when the model is given no hint. (4) The strongest verdict is `COMPLETE_WITHIN_SCOPE`, carrying snapshot, branch, PackSpec version and trigger-set version. (5) The gate never emits `ADMIT` or `can_generate=true` on its own.

### C. Lake and retrieval

**US-080 · P1 · Tenant-scoped conversation lake**
As an enterprise user, I want conversations, nodes and ledgers kept durably under my tenant, with deletion that actually propagates.
**Acceptance:** (1) An immutable raw zone holds turns and attachment references; a derived zone holds node PackSpecs, ledgers and manifests. (2) Every derived artifact is reproducible from raw content plus pinned versions, and a rebuild test proves it. (3) Storage reuses the existing PostgreSQL tenant ledger; cross-tenant reads and guessed IDs are denied in tests (US-043). (4) Deletion writes a tombstone that removes derived artifacts and invalidates dependent receipts. (5) Raw content is encrypted at rest and retention is configurable per tenant.

**US-081 · P1 · Addressable retrieval with a coverage receipt**
As an assistant, I want to fetch by ID and to know what a search did not return.
**Acceptance:** (1) Nodes are retrievable by node, branch and version ID, and by search. (2) Every response carries a coverage receipt: scope definition, nodes in scope, nodes returned, residual IDs not returned, excluded-by-rule count and `UNKNOWN` count. (3) An empty result distinguishes `NONE_IN_SCOPE` from `NOT_SEARCHED` and `INDEX_INCOMPLETE`. (4) A superseded version is never returned as current unless requested by version. (5) The receipt cannot report full coverage while the index lags the raw zone.

**US-082 · P1 · Assistant read-back tools over MCP**
As an AI assistant, I want read-only tools to explore the conversation lake during a turn.
**Acceptance:** (1) `conversation_manifest`, `conversation_get`, `conversation_search` and `conversation_ledger` are added to the reference contract in `mcp_server.py` and to the Netlify adapter. (2) Returned content is wrapped as data with actor class, authority and source anchors (invariant 13). (3) Each call is tenant-authorized and bounded in size and count. (4) Golden fixtures give identical results over stdio and the remote adapter. (5) No write tool for governance is exposed to the assistant.

**US-083 · P1 · Revision frontier revalidation**
As an operator, I want an amended rule to invalidate only what depended on it.
**Acceptance:** (1) A governance amendment or a changed lake source invalidates dependent node states and receipts along the dependency frontier, using the existing `depends_on` query. (2) A stale admitted conclusion is blocked until revalidated. (3) Unaffected branches keep their receipts. (4) Change-impact recall and false-invalidation rate are measured on the gold set.

### D. Evaluation and review surface

**US-084 · P0 · Frozen gold conversation set**
As a researcher, I want annotated real conversations fixed before any system output is seen.
**Acceptance:** (1) At least 30 authorized long threads, a count to be recalibrated after a pilot. (2) At least two annotators label constraints, supersessions, refinements, pivots and distant exceptions; raw and reconciled agreement are reported. (3) The set includes naturally occurring cases as well as injected ones. (4) The set is frozen and hashed before evaluation and hidden from whoever tunes the classifier and triggers. (5) Personal data handling and consent are documented.

**US-085 · P1 · Pre-registered comparison against full-context and summary baselines**
As a scientific reviewer, I want the tree compared fairly with the simple alternatives.
**Acceptance:** (1) Arms: C0 full transcript in context; C1 summary compaction; C2 tree without ledger; C3 tree with ledger and read-back gate; C4 C3 plus the differential fork test; plus the all-residual degenerate baseline. (2) Model version, token budget and latency ceiling are matched; C0 is also reported unbounded as a diagnostic ceiling. (3) Primary endpoints are stale-constraint violation rate and dropped-constraint rate; secondary are unnecessary forks, user interruptions, false `INCONCLUSIVE`, latency and cost. (4) Hypotheses, minimum practical effect and statistics are fixed before the holdout is opened. (5) If C0 or C1 wins at matched cost, that result is published.

**US-086 · P2 · Studio conversation tree view**
As a user, I want to see the tree and correct it.
**Acceptance:** (1) Studio shows nodes, PackSpec versions, fork and collapse events, and ledger dispositions per branch. (2) A user can lock, promote, amend or reopen a node; each action is attributed and append-only. (3) Residual and `UNKNOWN` spans are visible, not hidden behind the compiled view. (4) The view states that it shows declared structure, not validated meaning.

## Dependency path

| Batch | Stories | Exit gate |
|---|---|---|
| **G1 — Custody and governance** | 069, 070, 071 | A conversation round-trips byte-exactly; assistant text cannot bind |
| **G2 — Fork** | 072, 073, 084 | Ambiguous turns fork deterministically; classifier scored on frozen gold |
| **G3 — Ledger and gate** | 076, 077, 079 | Every span has a disposition; the gate fires without a model hint |
| **G4 — Lake and read-back** | 080, 081, 082, 078 | Assistant fetches by ID with a coverage receipt |
| **G5 — Economy and proof** | 074, 075, 083, 085 | Pre-registered comparison against C0 and C1 completed, whatever the result |
| **G6 — Surface** | 086 | Conditional on G5 |

The smallest slice that tests the idea is 069, 070, 073, 076, 079 and 084.

## Open decisions for the owner

1. **Tree store:** the first slice keeps conversation branches in a separate chain that follows the Gardener pattern. `Gardener.append` records every new branch as a research `HYPOTHESIS` claim in the Research Ledger, and a conversation branch is not a research claim (invariant 8). Unifying the two means making that ledger write optional in the Gardener, which is an IN_REVIEW component. Owner to decide.
2. **Live-branch cap:** default value and behavior at the cap.
3. **Comparator in US-074:** what counts as two answers agreeing.
4. **Gold set source:** which conversations may be used, and who the second annotator is.
5. **Relation to the proposal:** whether this epic is evaluated inside the Reversible Semantic Compilation paper or as a separate study. The paper's own acceptance gate targets documents, not conversations.

## Implementation evidence — slices 1 to 3

Package: `tools/conversation_tree/` · Guide: [CONVERSATION-TREE.md](CONVERSATION-TREE.md) · Tests: `tools/conversation_tree/tests/` (76 tests) · CI: `.github/workflows/conversation-tree.yml`

Local, deterministic, SQLite only. No model is called anywhere in the package. Statuses follow the FR.MD rule: a linked open PR is **IN_REVIEW**; nothing is DONE without merged review and independent evidence. "Has a direct test" below means a test exists in this package, not that the criterion is accepted.

| Story | Module | Criteria with a direct test | Not delivered |
|---|---|---|---|
| US-069 | `tree.py` | 1, 2 (randomized byte round trip, restart), 3, 4 | Reuse of the US-017 custody module; attachments by reference |
| US-070 | `tree.py` | 1, 2, 3, 4 (standing OPERATOR and USER rules apply to every branch and cannot be superseded), 5 | — |
| US-071 | `tree.py` | 1, 2 (turn-level anchors), 4, 5 | 3: only explicit supersession; no automatic conflict resolution |
| US-072 | `classify.py` | 1, 2, 3, 5 | 4: accuracy UNMEASURED |
| US-073 | `tree.py` | 1, 2, 3, 4, 5 | — |
| US-074 | `differential.py`, `tree.py` | 2, 3, 4, 5 | 1: the caller runs both branches; equal model and budget are checked from declared values only |
| US-075 | `tree.py` | 2, 3, 4 (refuses at the cap; the caller must ask the user) | 1 automatic witness detection; 5 metrics |
| US-076 | `tree.py` | 1, 2, 5; 3 by this package's own conservation check | 3 reuse of `rct_source_span_conservation.py`; 4 `CONTRADICTED` status |
| US-077 | `triggers.py`, `tree.py` | 1, 2, 4, 5 (a changed trigger set blocks a complete verdict) | 3 recall and false-trigger rate UNMEASURED |
| US-078 | `compaction.py` | 1, 2, 3 | 4, 5: probes check span availability only; no model answers a probe; independence is a declared source |
| US-079 | `tree.py` | 1, 2, 3, 4, 5 | — |
| US-080 | `lake.py` | 1, 2, 4; 3 on local SQLite only | 3 PostgreSQL tenant ledger and an authenticated principal; 5 encryption at rest and retention |
| US-081 | `retrieval.py` | 2, 3, 4, 5; 1 by turn, span and branch | 1 retrieval of a PackSpec by version ID; matching is lexical only |
| US-082 | `mcp_server.py` | 2, 3 (size bounds), 5 | 1 not added to `tools/activation_runtime/mcp_server.py` or the Netlify adapter; 3 tenant authorization; 4 parity |
| US-083 | `receipts.py` | 1, 3; 2 as a reported `STALE` status the caller must honor | 2 automatic blocking; 4 change-impact recall and false-invalidation rate |
| US-084 | `evaluation.py` | Tooling only: export a stored conversation, blank annotation template, two-annotator reconciliation with raw agreement, freeze with fingerprint, validator, scorer | Criteria 1 to 5: there are no threads, no annotators and no frozen set |
| US-085 | `comparison.py`, [pre-registration draft](CONVERSATION-TREE-PREREGISTRATION.md) | Harness only: constraint availability per arm at a matched word budget (C0, C2, C3) | Every criterion. C1 and C4 are NOT_RUN, the primary endpoint needs model answers, and the pre-registration is an unsigned draft |
| US-086 | `view.py` | 1, 3, 4 as a static read-only page; stored text is escaped | 2: no actions; not part of Studio |

No story is complete. The falsifiable claim at the top of this document is untested: no gold set exists and no model has been run.

**Decisions taken in the code that the owner may reverse**
- On `AGREE`, the differential test closes the **isolated** branch and keeps the merged one, because the merged branch retains the governance. Closing is reversible.
- A fork is a snapshot: a merged branch does not inherit amendments its parent makes after the fork. `receipts.dependents` reports when the parent has advanced.
- A deleted conversation ID is never reused within its tenant.

**Known limits**
- Obligation candidates are English lexical triggers and miss any constraint without a marker.
- The classifier is a small rule set. The only scores that exist come from a synthetic test fixture, which the harness labels as not evidence.
- The gate and manifest reason about which turns are loaded, not about what a model attended to.
- An empty inventory keeps the gate at `INCONCLUSIVE` by design.
- The lake's `principal` is caller-supplied; the host must authenticate it.
- Hash chains and triggers detect ordinary corruption; a database administrator can rewrite local state.
