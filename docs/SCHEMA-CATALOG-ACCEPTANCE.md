# US-002: versioned schema catalog acceptance

US-002 has four objective software criteria: a schema/example for each envelope,
major/minor identifiers, deterministic rejection of invalid input, and canonical
round-trip serialization. They do not claim semantic correctness or require a
merged PR or independent scientific signature. The catalog's shape checks never
authorize generation or establish domain truth.

The catalog contains ten entries: grammar, source, payload, transform, PackSpec,
verdict, receipt, operator AST, reviewed activation and source-observation graph.
Each entry has a local versioned JSON Schema and a committed JSON example.

## Implemented behavior

- The bounded loader checks the pinned local namespace, 2020-12 dialect and v1.x
  major/minor ID. Duplicate schema JSON keys and malformed/oversize files refuse.
- External $ref/$dynamicRef targets and nested base-URI changes refuse before
  retrieval. Local fragment references remain supported.
- The public validator rejects duplicate PackSpec and observation node IDs in
  addition to the existing type, enum, version and size constraints. This does
  not replace semantic/runtime checking or authentic source binding.
- Every committed fixture validates and canonical serialization round-trips.
  Repeated rejection probes cover duplicate IDs, unknown operators, invalid
  scalar shape, oversize payload and incompatible envelope major versions.

Run the actual catalog report:

~~~bash
python -m tools.activation_runtime.cli catalog
~~~

The report records all schema IDs, schema/fixture fingerprints, round-trip result
and deterministic rejection witnesses. It is software evidence, with semantic
admission INCONCLUSIVE and can_generate false. CI runs this command and uploads
its result as schema-catalog.json.

## Completion evidence

Only US-002 may use GITHUB_VERIFIED_SCHEMA_CATALOG/v1. It must record all four
criteria as verified, pin every catalog schema/example and the validator/acceptance
implementation, and bind the exact catalog report hash. The verifier recomputes
the report against the repository being audited, then checks actual live GitHub
source/run/job metadata. The successful pinned push run must have executed the
catalog report and all required test/audit steps without skips. Changed sources,
missing modules, forged/stale receipts, report drift or unavailable external
metadata refuses completion. A label or unit-test fixture is not acceptance.

Because the shared inventory auditor changes to add this criterion-specific
path, US-001's earlier completion must be reverified against the updated source.
Its previous accepted source/CI point remains in history; evidence is renewed
rather than silently accepted for changed code. Final closure is recorded only
after the implementation CI passes, followed by live-verification CI on the
completion metadata. Neither this path nor US-001's path supplies independent
acceptance for another research story or waives an explicit review requirement.
