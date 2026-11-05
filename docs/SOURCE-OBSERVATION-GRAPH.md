# Source observation graphs and finite typed transitions

US-016's source-observation graph composes the existing anchored observations
into a bounded typed AST. It checks actual role references and event dependencies,
then supports a reversible observation-ID transition. This is a QualityRag
reference representation. Canonical APX K/B/C/T/12G and FF-RCT parity remains
NOT_ESTABLISHED; a compatible interface or independent semantic validation has
not been supplied.

## Run the example

~~~bash
python -m tools.activation_runtime.cli observations \
  --source tools/activation_runtime/fixtures/observation-source.txt \
  --request tools/activation_runtime/fixtures/observation-request.json
~~~

The committed UTF-8 source, drafts and observation-graph.json example are authored
fixtures. The request has exactly observations and, optionally, rename. Each
draft contains observation_id, quote_start, quote_end, kind, value, roles,
polarity, quantity, unit, temporal_order and modality. Drafts are supplied
annotations, not facts inferred or authenticated by the type checker.

## Type and source rules

| Node kind | Role references | Temporal references |
|---|---|---|
| ENTITY | None | None |
| RELATION | Exactly subject and object, both existing ENTITY IDs | None |
| EVENT | Declared actor/recipient/beneficiary/subject/object, each an existing ENTITY ID | Existing distinct EVENT IDs |
| UNKNOWN | None; unsupported joins must remain unasserted | None |

For an event, temporal_order lists ordered antecedents. Every listed event
precedes the owning event, and adjacent antecedents retain their declared order.
Missing targets, wrong node kinds, duplicates, self references and cycles refuse.
A relation cannot target an unresolved UNKNOWN node as if it were an entity.
Unknown nodes and explicit unknown value/polarity/modality remain visible.
Conflicting annotations are not adjudicated as true by this structural checker.

Every node retains the original source SHA-256, exact quote/hash, character offsets
and UTF-8 byte offsets. Quantities retain their declared units; no unit conversion
or semantic normalization is performed. Value annotations are bounded JSON
scalars. Anchors prove which source bytes were quoted, not that an annotation's
meaning is correct. WELL_TYPED does not certify that a label follows from its quote.

The original UTF-8 source is limited to 65,536 bytes, the graph to 128 observations,
value strings to 4,096 characters, units to 64 characters and each event's ordered
antecedents to 32. Canonical serialized artifacts must fit the existing 512-KiB
budget. Malformed source and nonfinite values refuse. Source text outside the
observation inventory is not declared disposable: the full original remains the
residual/refetch requirement. An AST alone does not replace source custody.

## Reconstruction and transition

~~~python
ast = build(raw, drafts)
checked = check(raw, ast)
transformed, trace = rename(raw, ast, mapping)
original, _ = rename(raw, transformed, {new: old for old, new in mapping.items()})
~~~

check reconstructs every source anchor, join, temporal edge and unknown inventory
from actual bytes, then compares the entire canonical graph and its fingerprint.
Editing a quote, byte offset, graph inventory or declared hash cannot validate.
JSON Schema validates envelope shape; use check with original bytes to validate
the graph/source binding and cross-node types.

rename requires a total bijection over the observation IDs. It changes node IDs
and every role/temporal reference together, preserving all quotes, polarity,
quantity/unit, modality and raw source identity. The trace binds before/after AST
hashes, mapping hash and source hash. Applying the inverse mapping reproduces the
original AST hash. This proves a finite declared graph transformation, not
universal conservation of meaning or a new semantic codec.

## API and clients

POST /api/observations accepts source_sha256, observations and optional rename.
The principal must authenticate with read scope. The source is loaded and
hash-checked from its tenant's immutable object store before interpretation;
guessed cross-tenant IDs and corrupt originals refuse. A client cannot override
tenant, time, source hash or a verification flag. No inference or review authority
is created. The returned view is not automatically persisted; uploading an AST
through the source API separately requires write scope.

~~~python
result = client.observations(source_sha256=source_hash, observations=drafts)
~~~

~~~typescript
const result = await client.observations({source_sha256: sourceHash, observations: drafts});
~~~

Python, TypeScript and CLI return the same graph and transition for supported
wire numbers. Python can represent large JSON integers exactly. TypeScript now
rejects unsafe integer numbers in both requests and responses, including an
integer rounded by JSON parsing outside JavaScript's safe range. It never silently
returns a rounded quantity as an exact source observation. Large integers must
stay in Python or be represented explicitly as source text, preserving their
unknown interpretation rather than coercing them into numeric quantities.

Every result retains domain_validity UNKNOWN, canonical_apx_parity
NOT_ESTABLISHED and can_generate false. This endpoint cannot authorize activation,
resolve an unsupported diagnosis, endorse extracted relations or promote a model.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p test_semantic_ir.py -v
python -m unittest discover -s tools/activation_runtime/tests -p test_observation_service.py -v
~~~

Tests check deterministic canonical round-trip, exact UTF-8 anchors, wrong joins,
cycles, tampering, unknowns, quantities, bounded inputs and reversible ID mapping.
Real HTTP tests establish Python/TypeScript/CLI parity for construction/transition
and refusal for cross-tenant access, invalid joins, unsupported options and corrupt
source bytes. Independent annotation review and canonical semantic parity remain
separate acceptance requirements.
