# A correct quotation can still produce an unsupported answer

This reproducible, fully synthetic case demonstrates a missing-governing-exception failure mode. The rule is invented for testing and must not be mistaken for a real eligibility policy.

**Scenario:** A candidate meets a broad enrollment rule. A hypothetical exception requires a recent verification document. Retrieval has found the broad rule but has no evidence for the exception.

**Naive answer:** "Yes, the applicant is eligible." (unsupported, because the exception was not evaluated.)

**QualityRag behavior:** The PackSpec explicitly requires current-exception evidence. The gate reports `INCONCLUSIVE` with a `wgap` entry and does not invoke Spring AI's ChatClient. A future, independently verified source could resolve the gap.

Run the Python demonstration from repo root:
```sh
PYTHONPATH=sdk/python python examples/hidden-exception/demo.py
```

The demo does not prove an LLM would hallucinate, nor does it verify source truth. It demonstrates a deterministic missing-obligation prevention mechanism.
