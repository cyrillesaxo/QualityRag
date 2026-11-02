# Quickstart: Your First Evidence Decision

**Goal:** evaluate a PackSpec with two documents that share one origin and understand why the result is `INCONCLUSIVE`.

[Documentation home](README.md) · [Choose an SDK](README.md#choose-your-sdk) · [Decision reference](concepts.md)

## 1. Define a PackSpec

A PackSpec declares the evidence obligations a question must satisfy.

```json
{
  "id": "eligibility-demo",
  "version": "1",
  "requirements": [
    {
      "id": "rule",
      "min_independent_sources": 2,
      "max_age_seconds": 3600
    }
  ]
}
```

## 2. Submit evidence metadata

Both witnesses refer to **origin A**. Two documents are not necessarily two independent sources.

```json
[
  {
    "id": "w1",
    "requirement_id": "rule",
    "origin": "A",
    "source_ref": "doc:A#1",
    "status": "SUPPORTS",
    "observed_at": "2026-11-02T10:00:00Z"
  },
  {
    "id": "w2",
    "requirement_id": "rule",
    "origin": "A",
    "source_ref": "doc:A#2",
    "status": "SUPPORTS",
    "observed_at": "2026-11-02T10:00:00Z"
  }
]
```

## 3. Evaluate at a fixed time

Run the Python example from the repository root:

```bash
PYTHONPATH=sdk/python python examples/python_demo.py
```

For the data above, evaluate at `2026-11-02T10:05:00Z`:

```json
{
  "schema": "qualityrag.result/v0.1",
  "pack_id": "eligibility-demo",
  "pack_version": "1",
  "verdict": "INCONCLUSIVE",
  "findings": [
    {
      "requirement_id": "rule",
      "verdict": "INCONCLUSIVE",
      "independent_sources": 1,
      "reasons": ["INSUFFICIENT_INDEPENDENT_EVIDENCE"]
    }
  ]
}
```

> [!NOTE]
> The bundled `examples/python_demo.py` demonstrates the same type of decision with its own example identifiers. The JSON above corresponds to the PackSpec and witnesses shown on this page.

## 4. Interpret the result

**INCONCLUSIVE** means that, under the supplied metadata, the policy's requirement of two independent origins is not met. The application should report the missing evidence rather than call the answer generator.

Changing witness `w2` to declared origin `B` yields `ADMIT` *under the submitted metadata*. It does **not** prove that A and B genuinely are independent.

## 5. Integrate safely

1. Keep PackSpecs server-owned and versioned.
2. Enforce source authorization and provenance upstream.
3. Evaluate before model generation.
4. On `REFUSE` or `INCONCLUSIVE`, stop generation and return the bounded finding.
5. Reevaluate after relevant evidence or policy changes.

**Next:** [Choose your language](README.md#choose-your-sdk) · [Extended compiler and Wgap](concepts.md#extended-experimental-compiler) · [Troubleshooting](troubleshooting.md)
