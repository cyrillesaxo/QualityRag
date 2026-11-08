# Atomic evidence HTTP admission

The HTTP receiver can now be configured with `atomicInbox: new PgBalafonsEvidenceInbox(pool)`. It verifies the signed envelope and authenticated owner **without claiming replay separately**, then delegates to `atomicInbox.accept(event)`, which commits replay claim and durable inbox insertion in a single PostgreSQL transaction. Duplicate event IDs return HTTP 409. The earlier `replayStore + enqueue` path remains for compatibility but is **not crash-atomic** and must not be used in production.

The receiver is opt-in and not mounted in the running server. Production still requires authenticated service identity, deployment configuration, ordered revisions, and poison-event quarantine.
