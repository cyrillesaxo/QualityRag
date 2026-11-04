# QualityRag Research Memory v0.1 — a store for evidence, not optimistic status

**Purpose:** stop repeating the failure mode where merged code and green CI are reported as proof of a wider scientific claim. Research Memory is an append-only ledger of claims, evidence references, current assessments, and cross-claim links.

## Hosting decision (no Supabase required)

**Recommended:** PostgreSQL (self-hosted on an existing DigitalOcean Droplet or managed PostgreSQL) with relational source/witness graph edges. Add pgvector when there is an actual vector use case. Nothing in this initial evidence ledger requires a hosted database or an embedding model.

- **Start immediately:** local persistent SQLite using `tools/research_ledger/cli.py`. It is an inspectable reference implementation, not a globally available cloud database.
- **Production target:** PostgreSQL 16+ using `tools/research_ledger/postgresql.sql`. A PostgreSQL server is **not provisioned or migrated by this PR**. Migration SQL is intentionally create-only. Use a dedicated database, role and backups rather than attaching unaudited research writes to an existing production app.
- **Cost:** no new cloud resources are created by this PR. An existing droplet can host the service after capacity/security checks; running PostgreSQL on it adds resource and operations burden. A managed PostgreSQL service is an optional alternative.
- **Future:** optional pgvector or `tsvector` when source extraction/search requirements justify it. The canonical evidence/status ledger must not depend on vector embeddings or a particular LLM provider.

## What is stored

1. `research_claims`: stable hypothesis, implementation claim, experiment or decision IDs, plus current statement and hash.
2. `research_evidence`: evidence type, retrievable URI, content digest if independently available, metadata and evidence-record hash.
3. `research_events`: append-only assessment events with prior-event hash, actor and evidence IDs.
4. `research_links`: typed directed SUPPORTS, CHALLENGES, DEPENDS_ON, SUPERSEDES and QUALIFIES relationships between claims.

Assessments are `UNVERIFIED`, `IMPLEMENTED`, `TESTED`, `VALIDATED`, `REFUTED`, `SUPERSEDED` and `INCONCLUSIVE`. They are **assessments**, not automatically authenticated truths.

A CODE_COMMIT can support `IMPLEMENTED`; a CI_RUN or TEST_RESULT can support `TESTED`. **VALIDATED is deliberately prohibited** until an independent verifier with authenticated signed receipts and applicable validity criteria is integrated. Refutation/supersession requires recorded evidence. Confidence scores are not inferred from labels.

The storage is append-only under SQLite triggers and application checks. SHA-256 checksums and prior-event chaining detect accidental row modification, not a malicious database owner who can drop triggers/rewrite data. GitHub PR references are external links, not cryptographic source attestation.

## Run now (SQLite; no Supabase, no service or credentials)

From the repository root:

```sh
python tools/research_ledger/cli.py --db .research/progress.sqlite init

# Seed only milestones known to be merged; retain hypotheses as UNVERIFIED.
python tools/research_ledger/bootstrap_qualityrag.py --db .research/progress.sqlite

python tools/research_ledger/cli.py --db .research/progress.sqlite report --project QualityRag
python tools/research_ledger/cli.py --db .research/progress.sqlite verify
```

The bootstrap records PR #56 through #66 as implementation history and **does not mark them TESTED, VALIDATED or DEPLOYED** solely from merge evidence. It creates 11 capability entries and 3 unverified hypotheses. It is idempotent and does not silently rewrite existing entries.

Create additional claims and evidence:

```sh
python tools/research_ledger/cli.py --db .research/progress.sqlite claim \
  --id qualityrag.hypothesis.graph-economics --project QualityRag --kind HYPOTHESIS \
  --statement 'Typed graph construction reduces total work at equal evidence obligations.'

python tools/research_ledger/cli.py --db .research/progress.sqlite evidence \
  --id experiment.01 --kind MEASUREMENT \
  --uri 'https://github.com/cyrillesaxo/QualityRag/actions' \
  --description 'An experiment reference; not necessarily independent validation.'

python tools/research_ledger/cli.py --db .research/progress.sqlite assess \
  --id event.01 --claim qualityrag.hypothesis.graph-economics \
  --status INCONCLUSIVE --reason 'No independent matched-capability data yet' \
  --actor local-researcher --evidence experiment.01
```

Do **not** commit private local `.research/progress.sqlite` files. Back up the file privately and later migrate through a tested export/import process. This PR provides the PostgreSQL schema but **does not implement the SQLite-to-PostgreSQL data migration**; schema parity alone is not an end-to-end migration.

## PostgreSQL deployment foundation (not yet executed)

After selecting a dedicated private PostgreSQL instance, review and apply:

```sh
psql "$QUALITYRAG_RESEARCH_DATABASE_URL" -v ON_ERROR_STOP=1 -f tools/research_ledger/postgresql.sql
```

Store credentials in a protected host secret, never in GitHub or a browser bundle. Permit database connections only from trusted services or private networks, enforce TLS and separate application/administrative roles. Set automated backups, restores, migration checks, monitoring and authentication before any multi-user deployment. The PostgreSQL schema creates `research` tables and a read-only current-status view; it does **not** provide a production API or data transfer from SQLite. The SQLite CLI intentionally does not pretend to be a connected PostgreSQL client.

## Required research habits

- A merged PR is **implementation evidence**.
- Automated test success is **test evidence**, not a production acceptance test.
- A local smoke test is **runtime evidence for that host and timestamp** only.
- Independent dataset results with provenance, evaluator independence and declared scope are prerequisites for scientifically **validated** claims.
- A contrary result must create a CHALLENGES/QUALIFIES/SUPERSEDES relation and a new assessment event; previous history must stay accessible.
- An assistant summary must be derived from the ledger's as-of state and name any unavailable evidence—not merely from previous assistant messages.

## Tests and limits

```sh
python -m unittest discover -s tools/research_ledger/tests -p 'test_*.py' -v
```

Current implementation has append-only SQLite reference persistence, but **not** a deployed cloud database, automatic GitHub webhook sync, signed review identities, semantic embedding ingestion, multi-tenant IAM, backup restores or a cloud API. Graph edges are typed claim relationships, not factual entailment. The initial bootstrap covers QualityRag, not all past APX/FF-RCT/AST work; importing those requires source references and explicit reconciliation rather than trusting conversational recollection.
