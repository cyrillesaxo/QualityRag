# Balafons ingestion HTTP adapter (not deployed)

`createBalafonsIngestHandler` is an opt-in Node HTTP adapter for server-to-server signed source events. It must be mounted **only** behind a trusted gateway with `resolveOwner(req)` verifying a real Balafons service credential and independently establishing the owner's identity. The test uses an untrusted header as a fixture **only**; never use that strategy in production. The default registry does not mount this handler.

The adapter validates the event signature, tenant ownership, timestamp, source revision and replay, then passes accepted events to an injected `enqueue` implementation. Production enqueue must be durable and idempotent; a database-backed replay claim and queue insertion must be transactional to avoid lost events after a crash. Indexing, retrieval ACL enforcement, Google OAuth callback, Drive sync, and disconnection remain unimplemented.

Never expose the signing secret in Balafons web bundles. Ensure independent service authentication, HTTPS, private tenant partitioning, source permission refresh, deletion tombstones, and two-user integration tests before enabling this route.
