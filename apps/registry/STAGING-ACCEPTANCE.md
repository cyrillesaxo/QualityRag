# Staging acceptance: signed QualityRag registry

This test exercises a disposable local staging simulation with PostgreSQL 16, a live registry Node process, and test-issued OIDC JWTs. It does not deploy cloud infrastructure.

## Acceptance coverage

- Run the existing PostgreSQL migration and start the registry in signed-only OIDC mode.
- Authenticate distinct author, reviewer, publisher, and reader JWTs using an ephemeral JWKS.
- Reject wrong audiences and insufficient permissions.
- Stage, approve and publish an Ed25519 signed policy via HTTP API.
- Resolve the exact signed bundle and verify its signature.
- Restart the Node process while retaining PostgreSQL state; check policy recovery.
- Reject sequence reuse, publish the next version, and prohibit downgrade after another restart.
- Validate the persisted sequence and audit event order.

The integration test generates ephemeral keys and a unique service ID. It must never run against production data.

## Run

From the repository root:

```bash
npm --prefix apps/registry install
DATABASE_URL="$PG_TEST_DATABASE_URL" node apps/registry/src/migrate.js
PG_TEST_DATABASE_URL="$PG_TEST_DATABASE_URL" node --test apps/registry/test/staging-http-recovery.test.js
```

The Studio and Registry GitHub Actions workflow provisions PostgreSQL, executes migrations, and runs this integration test as part of the registry suite.

## Remaining deployment work

A remotely accessible staging service, provider-managed database, genuine identity-provider configuration, externally stored trusted signing keys, backup/restore drill and independently maintained application sequence floors are not provided by this CI test. No claim is made that a signed evidence record establishes the truth or completeness of an original APX specification.

Research: Cyrille Eloundou / APX, https://apx.guide/.
