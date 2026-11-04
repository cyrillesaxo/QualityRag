# Research Memory v0.2 — PostgreSQL and Neon integration

## Status

This milestone adds **actual PostgreSQL read/write operations**, a strict SQLite-to-PostgreSQL importer and a disposable PostgreSQL 16 integration test in GitHub CI. The same client runs against Neon, self-managed PostgreSQL and other providers.

**Not included:** a hosted Neon project, database credentials, a deployed server, a browser-exposed API, verified reviewer identities, pgvector, authentication or an automatic GitHub webhook.

The research truth rule remains unchanged: **MERGED != TESTED != DEPLOYED != INDEPENDENTLY VALIDATED**. Even all-green PostgreSQL CI only establishes the tested interactions on the ephemeral CI database.

## Create a private Neon database

Use the connected Neon application to create or select a dedicated database for QualityRag research. Keep it separate from existing LexyRead/Supabase production databases. Obtain the **connection string through the provider's secrets mechanism**, never paste it into chat, GitHub, logs or a browser bundle.

The provider app connection in ChatGPT does not automatically make its secrets available to local CLI scripts. On a trusted deployment host, set:

```sh
export QUALITYRAG_RESEARCH_DATABASE_URL='postgresql://<private-credentials>/<database>?sslmode=require'
```

The value shown above is a **placeholder**, not a configured connection.

Install the optional PostgreSQL driver:

```sh
python -m pip install 'psycopg[binary]>=3.2,<4'
```

Apply the create-only migration to that dedicated database, preferably from a separate migration/owner role:

```sh
psql "$QUALITYRAG_RESEARCH_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f tools/research_ledger/postgresql.sql
```

PostgreSQL stores the existing canonical UTC timestamp strings as **text**, preserving exact event-hash preimages from the SQLite ledger. These values are deliberately not parsed into a differently formatted `timestamptz`. The read-only `research.current_claim_status` view reports latest assessments. The four tables use update/delete rejection triggers. This schema does not implement RLS; **do not expose the database directly to untrusted clients**. Protect it with an authenticated server-side service and least-privilege DB roles.

## Bootstrap with a local source of provenance

Generate a local, inspectable file (this is NOT a cloud deployment):

```sh
mkdir -p .research
python tools/research_ledger/cli.py --db .research/progress.sqlite init
python tools/research_ledger/bootstrap_qualityrag.py --db .research/progress.sqlite
python tools/research_ledger/cli.py --db .research/progress.sqlite verify
```

Preview an import:

```sh
python tools/research_ledger/migrate_sqlite_to_postgres.py \
  --sqlite .research/progress.sqlite --dry-run
```

Execute the migration:

```sh
python tools/research_ledger/migrate_sqlite_to_postgres.py \
  --sqlite .research/progress.sqlite
```

The importer uses PostgreSQL transactions and an advisory lock; rejects conflicting immutable rows; checks SQLite SHA integrity and event chains before import; preserves event timestamps and hashes; and can be rerun idempotently.

This v0.2 migration is designed for the *v0.1 SQLite schema*. It does not automatically import arbitrary APX, FF-RCT, files, source annotations or visual data; these require separate source-of-record reconciliation and authorization.

## Programmatic usage (server-side only)

```python
import os
from postgres import connect, claim, evidence, assess, progress

with connect(os.environ["QUALITYRAG_RESEARCH_DATABASE_URL"]) as db:
    report = progress(db, project="QualityRag")
    print(report["counts"])
```

Use `PYTHONPATH=tools/research_ledger` for the example or package the module as a private service dependency.

Additional functions `claim`, `evidence`, `assess` and `link` support the same bounded input contracts as the SQLite reference implementation. **Independent VALIDATED status remains forbidden** until a trusted evaluator with signed/authenticated receipts is built.

## Actual PostgreSQL integration verification

GitHub workflow `.github/workflows/apx-semantic-store.yml` now has a `research-postgres` job using the **PostgreSQL 16 Docker service**, a throwaway CI-only password, the real migration SQL, and Python `psycopg`.

It checks claim/evidence/assessment writes, rejection of fabricated research validation, immutable-row protection, import dry-run and idempotency, preserved hashes, and conflict refusal. Tests are gated on `QUALITYRAG_TEST_DATABASE_URL` so local SQLite-only tests run without a server.

Run locally with a **disposable database**, never a production Neon instance:

```sh
QUALITYRAG_TEST_DATABASE_URL='<disposable-test-dsn>' \
 python -m unittest discover -s tools/research_ledger/tests \
  -p test_postgres_integration.py -v
```

## Deployment acceptance criteria

Do not call the hosted store operational until all have been observed against the **actual target Neon database**:

1. Correct project and database selected; migration SQL applied without errors.
2. Service credentials secured and scoped to minimum required privileges.
3. The seeded research history successfully imported and counted.
4. Repeat import produces zero duplicate/new rows.
5. Readback returns exactly 11 `IMPLEMENTED` capabilities and three `UNVERIFIED` hypotheses from the v0.1 bootstrap, with evidence references.
6. A source-versus-target integrity comparison succeeds.
7. Backups, restore trial, tenant authorization and server-side API are reviewed before production use.

There is **no automatic sync** between the SQLite file and Neon. The SQLite importer is a one-way initial migration; running two writers on both stores requires a separate reconciliation protocol. Do not write both concurrently.

## Important limitations

This implementation is **not** production-ready merely because the schema and CI pass. Database access, independent validation, embeddings, durable file ingestion, reviewed source graph and authenticated workflow integrations still need to be supplied and verified. PostgreSQL triggers deter accidental rewriting but do not prevent a privileged database administrator from removing the triggers.
