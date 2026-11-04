# Signed PostgreSQL research validation

US-036 now has a PostgreSQL implementation of scope-bounded signed validation.
This is a private database integration for trusted host code. A signed reviewer
approval authenticates its author and scope; it does not prove domain truth.

Apply tools/research_ledger/postgresql.sql to the dedicated research database.
The create-only migration adds an append-only research.validation_receipts table.
Existing claim, evidence and assessment hashes are unchanged.

Use tools.activation_runtime.postgres_validation.review_context to prepare the
review payload from the stored claim/evidence records. Host configuration must
provide a stable, unique ledger_id, the tenant, the reviewer's public-key trust
map and the proposer's public key. Bind ledger_id to the deployment and preserve
it with database backups. Distinct deployments must not share it inadvertently.
Keys and the ledger identity are never derived from uploaded documents.

The reviewer signs that exact context using authority.review_binding. It binds:

- Ledger identity, database name, tenant, event ID and event actor.
- Claim record hash, every selected evidence record hash and current chain head.
- Explicit validation scope and the VALIDATED assessment purpose.

Call postgres_validation.validate_claim with the envelope and trusted host
configuration. The PostgreSQL adapter locks the claim, requires review plus
observed/test evidence, verifies stored record hashes and the chain, checks the
signature, expiry, proposer/reviewer separation and actor identity, then inserts
the receipt and assessment in one transaction. A unique nonce blocks concurrent
replay. A deferred event foreign key and transaction rollback keep failed writes
from burning the approval. If an intervening assessment changes the chain head,
obtain a fresh review. Backdated appends are refused.

Caller booleans, missing review evidence, untrusted keys, altered scope, stale
reviews and expired signatures cannot authorize validation. PostgreSQL owners
remain inside the trust boundary: SQL triggers and hashes are not protection
against a privileged administrator replacing schema or data.

SQLite approvals are bound to their original environment. The SQLite-to-Postgres
importer refuses ledgers containing VALIDATED events rather than copying a status
without destination authority. Preserve the source ledger; destination admission
requires a separately reviewed migration design and fresh destination review.

## Verification

The activation CI job provisions PostgreSQL 16 and supplies
QUALITYRAG_TEST_DATABASE_URL to both the activation and Research Ledger suites.
No database is provisioned in the user's cloud account.

Locally, set that variable only to a disposable test database and run:

~~~bash
python -m pip install -r tools/activation_runtime/research/requirements.lock.txt
python -m unittest discover -s tools/activation_runtime/tests -p 'test_postgres_validation.py' -v
python -m unittest discover -s tools/research_ledger/tests -p 'test_postgres_integration.py' -v
~~~

Tests use actual signatures, actual PostgreSQL transactions and two concurrent
database connections. They cover successful receipt readback, immutable receipts,
wrong scope/tenant/ledger/actor/key/expiry, same-key self-review, replay, missing
evidence, corruption, forced write failure with approval reuse, stale reviews,
backdated appends and validation laundering through migration. Without a DSN,
these integration tests explicitly skip. Authored test approvals are never
reported as independent scientific evidence.
