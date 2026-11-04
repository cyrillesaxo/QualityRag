# Bounded activation research runtime

This package connects existing QualityRag mechanisms into an executable research
slice. It does not provide a Semantic Codex video codec or production admission.

## Run

From the repository root with Python 3.12:

~~~bash
python -m pip install -r tools/packspec_compiler/requirements.txt -r tools/activation_runtime/requirements.txt
python -m unittest discover -s tools/packspec_compiler -p 'test_finite_activation.py' -v
python -m unittest discover -s tools/activation_runtime/tests -p 'test_*.py' -v
python -m tools.activation_runtime.demo --out /tmp/activation-demo
~~~

Use a fresh output directory. The demo produces four explicitly authored
synthetic examples, a real compiled ConstraintIR, exact source custody objects,
actual reconstructed field values, compatibility and gate receipts. Running
it twice yields the same structural receipt bytes. Ephemeral demo keys are
discarded and have no real reviewer authority.

## Implemented paths

- contracts: eight local JSON Schemas for source, payload, grammar, operator
  AST, transform, ConstraintIR shape, verdict and receipt. Runtime checks remain
  responsible for semantic type compatibility, duplicate IDs, fingerprints,
  full bijections and authorization. No remote schema resolver is used.
- artifacts: host-scoped tenant store, immutable content addresses, atomic
  publication, Ed25519-signed manifest, pinned runtime/policy/source/artifact,
  transitive data-module resolution, expiry, revocation and version floor.
- pipeline: actual canonical RCT induction, held-out validation, versioned
  input/policy cache invalidation, compiled artifact bytes and measured lookup/
  compile time; actual existing PackSpec gate; strict CSV ingestion with row
  and physical line anchors.
- gardener: append-only PROPOSE/CHALLENGE/TEST/SYNTHESIZE/PRUNE/REOPEN,
  bounded parent DAG, deterministic replay, corruption checks, and claims in
  the existing Research Ledger. Syntheses always begin UNVERIFIED.
- economics: explicit full lifecycle components with OBSERVED/ASSUMED/UNKNOWN
  distinctions and a fidelity-filtered Pareto frontier. No inferred savings.
- media: real lossless AV1 encoding and normalized frame-byte comparison.
  Requires FFmpeg/ffprobe, a local clip, rights reference and split family.
  Audio, semantic identity, timing, energy and independent rights verification
  are explicitly outside this measurement.
- native_apx: executes original, SHA-pinned APX WBC and RCoC TypeScript using
  Node 24; no Python reimplementation. Configure QUALITYRAG_APX_ROOT for tests
  against APX commit 9a4f8a3e4a3fe77d576369217525e54d0162b8b0.
  Required files are packages/apx-wbc/src/index.ts,
  packages/apx-rcoc/src/index.ts, and
  packages/apx-rcoc/src/canonical-taxonomy.ts.

WBC requests carry a complete finite decision table for at most eight witnesses.
RCoC requests must explicitly supply known applicability for all twelve canonical
G coordinates. The adapter will not convert unknown applicability to false.
Missing original APX sources fail; optional tests SKIP without a configured
checkout. CI explicitly checks out that pinned APX source.

## Trust boundary

The application must authenticate its principal and derive tenant identity on
the host. A tenant string supplied by an end user is not authorization. Protect
the store root from untrusted filesystem writers and preserve it on durable
storage. Content digests are integrity checks, not custody or truth attestations.

Trusted manifest keys and the minimum sequence are host configuration. Removing
a key revokes it. An authorized rollback must remain above the sequence floor
and must have a valid signature, supported runtime and matching content/policy.
Registry objects are inert data; no plugin, model import or downloaded code is
executed by the decoder.

A release signature authenticates bytes and scope. It does not authenticate
PackSpec completeness, reviewer independence or clinical/legal correctness.
Research output is labeled as such; can_generate stays false. Fallback never
releases failed output. Production signing keys, approved review authority,
persistent service authorization and independently validated domain evidence
are still required for production admission.

## Remaining research and engineering

See capabilities.json and FR.MD. The corpus, actual shared-grammar video
encoder/decoder, neural codec baseline, agent execution sandbox/model providers,
streaming/device runtime, Gardener review UI, SDK parity, and independent
controlled evaluation are not implemented by these modules. Passing these
tests cannot satisfy those stories.
