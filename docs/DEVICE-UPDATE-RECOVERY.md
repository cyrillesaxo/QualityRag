# Durable module downloads and signed rollback

US-027's filesystem reference supports recoverable downloads and atomic signed
activation on POSIX hosts. It does not establish mobile/TV platform support,
energy use, thermal behavior, network performance or production deployment.

## Resume and concurrency

A transfer's immutable metadata pins its content address and total byte count.
The declared total must be between one and two million bytes; offsets and sizes
are integers, excluding booleans. A changed total or stale offset refuses before
writing. Each chunk is flushed to disk. Metadata and activation pointers use
atomic replacement and directory fsync. Publication persists the verified object
before deleting recovery state.

A nonblocking per-tenant file lock serializes download, cleanup and activation
mutations, including separate updater processes. A busy update raises ValueError;
the host should retry after querying progress, with a bounded retry policy.
There is no indefinite lock wait. Different tenants have separate state and
locks. POSIX flock and directory fsync support are required; no cross-platform
locking fallback is claimed. Filesystem administrators remain trusted.

~~~python
updater = ModuleUpdater(root, tenant=authenticated_tenant)
status = updater.progress(module_sha256)
# PARTIAL exposes the durable downloaded_bytes offset and pinned total.
# Reopen the transport at that offset before supplying the next chunk.
result = updater.append(module_sha256, chunk, offset=offset, total=total)
~~~

The complete object is checked against SHA-256. A corrupt completed download is
discarded, allowing a clean retry. A failure before object publication preserves
the complete partial file; retry with an empty chunk at the reported end offset.
If publication succeeded but its reply or cleanup failed, an exact retry reuses
the hash-verified object. Conflicting retry bytes or totals refuse. Symlink locks,
transfer files and metadata are not followed. Corrupt cached objects refuse.

Earlier unbound partial files cannot establish their original total. They refuse
resume until the host explicitly invokes discard_partial(address). This abandons
transfer data and metadata while preserving verified cached objects. Check
progress before fetching a new chunk to avoid an unnecessary retransmission.

## Byte accounting

| Field | Meaning |
|---|---|
| downloaded_bytes | Durable usable transfer bytes so far; cumulative, not additive across calls |
| received_bytes | Bytes supplied in this successful append call, including exact retransmissions |
| written_bytes | Bytes appended to the partial file in this call; zero for a cache hit |
| cached_object_bytes | Verified object content bytes currently available, excluding filesystem overhead |
| cache_hit | Completion reused an existing verified object |

progress reports local state and cached bytes without requesting content over
the network. These fields do not include transport headers, failed request
traffic, filesystem allocation, electricity, currency costs or device telemetry.
The host must measure those separately; byte counts are not cost estimates.

## Activation and explicit rollback

activate re-verifies the signed manifest, tenant, source, policy, artifact,
transitive module graph, signature lifetime, trusted keys and host minimum
sequence on every call. Only a module covered by that manifest can become active.
The atomic pointer records its sequence, manifest fingerprint, cached bytes and
previous module address. Failed validation and failed pointer replacement preserve
the prior activation. After restart the prior pointer is read under the same lock.

Calling activate with an older signed release is an explicit rollback request.
It succeeds only if the release is compatible, unexpired, trusted and at or above
the host's configured floor. The updater does not automatically raise that floor
to the last observed version: that would prevent authorized rollback. The host
owns durable version policy and key revocation; a previous-address field alone
never authorizes rollback. No executable module content is evaluated here.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_device*.py' -v
~~~

Tests use real temporary files and independent updater instances, racing writers,
restart recovery, injected publication failures, lost replies, altered totals,
legacy migration, symlink refusal and an actual signed old/new/rollback sequence.
Revoked, expired, policy-mismatched and below-floor releases preserve the active
pointer. These are authored software checks; physical-device A/B reconstruction,
bandwidth, cache and update-cost measurements remain acceptance requirements.
