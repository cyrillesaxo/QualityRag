# Typed ConstraintIR v0.1

**Research lineage:** Cyrille Eloundou, APX — https://apx.guide/. This is an experimental QualityRag intermediate representation, not a complete executable APX grammar.

The source inspector extracts candidate clauses from YAML, JSON, and text-bearing PDFs. Typed ConstraintIR preserves the manually reviewed classification and its source provenance while separating what the v0.1 metadata evaluator can check from what it cannot.

## Supported node kinds

| Kind | Fields | Runtime |
| --- | --- | --- |
| EVIDENCE_PRESENCE | Requirement ID, reported independent-source count | PROJECTION_ONLY: may become a v0.1 evidence requirement |
| TEMPORAL | BEFORE, AFTER, WITHIN, EXPIRES_AT; time anchor; optional interval | DEFERRED |
| AUTHORITY | Role, scope | DEFERRED |
| PROBE | Probe ID, expected artifact type | DEFERRED, unbound executor |
| PREDICATE | Untrusted source expression | DEFERRED, never executed as code |

Every node has the cited candidate ID, source location, quotation, quotation SHA-256, source file SHA-256, reviewer label, rationale, and approval flag. Approval is a user-declared label, not authenticated authorization.

The typed IR summary explicitly reports semantic_constraints_executed = 0. It **cannot** certify that the source PackSpec is complete, because extraction is heuristic and may miss relevant clauses.

## Workflow

Install compiler requirements:

~~~bash
python -m pip install -r tools/packspec_compiler/requirements.txt
~~~

Inspect the original APX source and produce an **unapproved** typed mapping worksheet:

~~~bash
python tools/packspec_compiler/compiler.py source.yaml \
  --out inspection.json \
  --typed-draft-out typed-review.json
~~~

Manually edit the typed-review.json mapping. Each selected candidate requires an appropriate node kind, its typed parameters, approved = true, reviewed_by, and a substantive rationale.

Example reviewed rules (source hash and candidate IDs must be copied from the actual inspector output, not invented):

~~~json
{
  "schema": "qualityrag.typed-mapping/v1",
  "source_sha256": "ACTUAL_SOURCE_HASH_FROM_INSPECTION",
  "rules": [
    {
      "candidate_id": "C0001",
      "node_id": "cold-recall-witness",
      "kind": "EVIDENCE_PRESENCE",
      "parameters": {
        "requirement_id": "cold-retrieval-evidence",
        "min_independent_sources": 1
      },
      "approved": true,
      "reviewed_by": "domain-reviewer",
      "rationale": "Require a witness record without claiming mastery certification"
    },
    {
      "candidate_id": "C0002",
      "node_id": "recall-after-attempt",
      "kind": "TEMPORAL",
      "parameters": {"relation": "AFTER", "anchor": "learner-attempt"},
      "approved": true,
      "reviewed_by": "domain-reviewer",
      "rationale": "The sequence requirement remains deferred until a trusted temporal runtime exists"
    }
  ]
}
~~~

Then compile the typed record and optional **evidence-only** QualityRag policy:

~~~bash
python tools/packspec_compiler/compiler.py source.yaml \
  --out inspection.json \
  --typed-mapping typed-review.json \
  --ir-out typed-ir.json \
  --typed-policy-out evidence-policy.json \
  --typed-policy-id learner-evidence
~~~

An all-deferred IR cannot produce a v0.1 evidence policy. No temporal rule, authority relation, executable probe, or semantic predicate is silently converted to a passing evidence requirement. The policy output, if produced, can be supplied by the existing internal/property/file/Studio PackSpec sources.

## Example boundaries from supplied APX documents

**SEMLOAN:** cold retrieval evidence can require an actual evidence record, but the timing relation and learner trajectory must remain deferred.

**Question Fan:** an optional question's assumption trace may be represented as evidence; user consent, choice-before-action and zero-fan rules are not currently enforced.

**FFI:** source custody and corroboration may be represented as evidence categories; a discriminating probe is recorded as unexecuted until a trusted measurement runtime exists.

**FFI Teacher:** an instructional code artifact can be required as evidence; cross-framework back-translation must be executed separately.

**Software-selling:** a pilot and comparison artifact may be required, but the k0–k4 depth ladder and causal validity of commercial claims remain unsupported.

## Correctness and security limitations

- Review labels and source digests do not authenticate reviewers or document publishers.
- Source excerpts and provenance references cannot guarantee correct parsing or semantic applicability.
- Typed PREDICATE expressions are inert, untrusted text and must not be passed to eval.
- Temporal, authority and probe records are **DEFERRED**, even when a reviewer approves their representation.
- The IR is deterministic for an identical source, mapping and parser output; SHA-256 is an integrity fingerprint, not a signature.
- A QualityRag ADMIT verdict is about declared evidence metadata, not APX-level semantic truth.

Tests: python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py'
