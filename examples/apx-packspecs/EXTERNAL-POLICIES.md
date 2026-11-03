# External PackSpec files: five training projections

The `policies/` directory holds **five standalone JSON PackSpecs** derived as **narrow evidence-checking projections** of the uploaded APX specifications. They are valid QualityRag v0.1 policies, **not direct conversions or faithful implementations of the full SEMLOAN, Question Fan, FFI, FFI Teacher or software-selling governing contracts**.

## Try file-based loading (Python)

```bash
PYTHONPATH=sdk/python python examples/apx-packspecs/external_example.py
PYTHONPATH=sdk/python python -m unittest discover -s examples/apx-packspecs -p 'test_*.py'
```

The same fixtures are used by native example tests in all ten SDK languages. This additional experiment verifies that the **file** and **property** sources produce the same fifteen expected decisions.

To load one training policy from an external file:

```python
from qualityrag.sources import from_properties
from qualityrag import evaluate

source = from_properties({
    "qualityrag.packspec.source": "file",
    "qualityrag.packspec.path": "examples/apx-packspecs/policies/ffi-teacher.json",
})
result = evaluate(source(), extracted_evidence, as_of="2026-11-02T10:05:00Z")
if result["verdict"] != "ADMIT":
    # Reject unsupported answer generation.
    pass
```

`extracted_evidence` is an application-provided list of verified witness metadata; this snippet assumes you have already retrieved and classified the source documents. In practice, a true RAG integration must authenticate witness sources, evaluate semantic applicability, and decide which policy applies. A QualityRag `ADMIT` **does not** license teaching mastery, research truth, or marketing claims.

To switch sources, configure `qualityrag.packspec.source` to `internal`, `property`, `file`, or `studio` according to [source-selection guidance](../../docs/PACKSPEC-SOURCES.md). Studio is a development-grade registry with no production-signed bundles.

**Research attribution:** Cyrille Eloundou and [APX](https://apx.guide/).
