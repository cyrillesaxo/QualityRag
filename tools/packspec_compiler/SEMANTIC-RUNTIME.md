# Bounded semantic runtime v0.1

**Research lineage:** Cyrille Eloundou / [APX](https://apx.guide/).

This first runtime adds deterministic checking for explicitly reviewed **temporal relationships** and **bounded probe values**. It is not a general semantic interpreter, an LLM, a forensic evidence engine, or an authenticated policy service.

## Supported typed checks

| Constraint | Required binding | Decision |
| --- | --- | --- |
| TEMPORAL BEFORE | Two identified event timestamps | ADMIT when subject is strictly before anchor |
| TEMPORAL AFTER | Two identified event timestamps | ADMIT when subject is strictly after anchor |
| TEMPORAL WITHIN | Subject, anchor and maximum seconds | ADMIT when subject occurs from anchor through duration |
| TEMPORAL EXPIRES_AT | Anchor expiry timestamp and as-of | ADMIT strictly before expiry |
| PROBE EQUALS | Probe ID, artifact type, field, expected primitive | ADMIT when observed value matches with same type |
| PROBE NUMERIC_RANGE | Probe ID, artifact type, field and inclusive numeric bounds | ADMIT when observed number lies in range |
| AUTHORITY, PREDICATE, EVIDENCE_PRESENCE | — | INCONCLUSIVE: handled elsewhere or not implemented |
| Unbound legacy TEMPORAL/PROBE nodes | — | INCONCLUSIVE: not executed |

An explicit failed temporal/probe condition returns **REFUSE**; missing events, malformed timestamps, missing receipts or unsupported types yield **INCONCLUSIVE**. The aggregate returns REFUSE if any check fails, otherwise INCONCLUSIVE if any check is unresolved, otherwise ADMIT.

**ADMIT means only that these defined comparisons passed on supplied observations.** It does **not** prove the observations, source provenance, training success, regulatory compliance or full APX semantics. A source reference is a plain string and not authenticated.

## Example — SEMLOAN cold recall

In the reviewed typed mapping, replace generic temporal/probe nodes with explicitly bound parameters. The compiler still requires a source fingerprint, candidate locations, manual reviewer and rationale.

~~~json
{
  "kind": "TEMPORAL",
  "parameters": {
    "relation": "AFTER",
    "anchor": "learner-attempt",
    "subject": "cold-retrieval"
  }
}
~~~

~~~json
{
  "kind": "PROBE",
  "parameters": {
    "probe_id": "recall-evaluation",
    "artifact_type": "TEST_RESULT",
    "check": "NUMERIC_RANGE",
    "field": "score",
    "minimum": 80,
    "maximum": 100
  }
}
~~~

The observation file supplied to the runtime could be:

~~~json
{
  "events": {
    "learner-attempt": {
      "at": "2026-10-30T10:00:00Z",
      "source_ref": "attempt#25"
    },
    "cold-retrieval": {
      "at": "2026-11-02T09:00:00Z",
      "source_ref": "quiz#48"
    }
  },
  "probes": {
    "recall-evaluation": {
      "artifact_type": "TEST_RESULT",
      "source_ref": "graded-quiz#48",
      "values": {"score": 90}
    }
  }
}
~~~

Assuming those two nodes were compiled from an approved mapping to typed-ir.json:

~~~bash
python tools/packspec_compiler/semantic_runtime.py \
  --ir typed-ir.json \
  --observations observations.json \
  --as-of 2026-11-02T10:05:00Z \
  --out semantic-checks.json
~~~

The resulting document contains a per-node verdict and reason, an aggregate verdict, an IR fingerprint, and an explicit notice that observations were not independently authenticated.

## Integration guardrail

An enterprise RAG application must combine this report with the **existing evidence-completeness gate**, and must not authorize generation when either reports REFUSE or INCONCLUSIVE. No automatic trust transfer is provided between the two evaluators. Do not mistake separate ADMIT results for full policy completeness; reviewer/source authority, applicable versions, and undeclared constraints still require governance.

An older IR without explicit temporal subjects or probe assertions remains deferred. No attempt is made to infer missing parameters from free-form source prose. There is no use of eval or arbitrary probe executors.

## Tests

~~~bash
python -m pip install -r tools/packspec_compiler/requirements.txt
python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py'
~~~

Tests cover chronological order, expiry boundary, range bounds, type mismatches, missing evidence, tampering, unbound legacy nodes, deferred authority and CLI receipts.

**Remaining work:** authenticated event and probe attestation, canonical signed policy bundles, independence/authority checks, reproducible probe execution, complete APX predicate evaluation, and cross-language runtime conformance.
