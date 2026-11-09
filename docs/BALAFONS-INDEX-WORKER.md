# Balafons indexing worker (reference)

`BalafonsIndexWorker.processBatch(limit)` consumes pending signed-evidence inbox records and updates the PostgreSQL full-text index in the **same database transaction**. It validates tenant ownership and source ACL, serializes writes per source, removes stale chunks on revision replacement, and processes deletion tombstones. On error, the batch rolls back and remains pending.

**Not production complete:** event ordering is not guaranteed across separate batches, and a late older event may overwrite a newer revision. Source sequencing/version checks and deletion tombstone high-water marks are required before enabling unattended ingestion. A malformed event currently blocks the batch; implement bounded retries and quarantine. Also integrate atomic signature validation plus inbox acceptance in the HTTP receiver, enforce live ACL checks, and wire the actual PackSpec evaluator and answer endpoint. No worker is currently deployed or scheduled.
