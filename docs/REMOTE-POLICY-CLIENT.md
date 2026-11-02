# Java remote policy resolution — experimental

The Java SDK includes `io.qualityrag.RemotePolicyClient` for resolving a versioned, approved PackSpec from QualityRag's central registry.

```java
var client = new RemotePolicyClient(
    URI.create("https://your-registry.example"),
    System.getenv("QUALITYRAG_SERVICE_TOKEN")
);
var binding = client.resolve("claims-api", "production");
var verdict = SemanticCompiler.evaluate(binding.policy(), evidence, Instant.now());
```

**Fail closed:** a missing binding, non-200 response, network error, invalid envelope or digest mismatch throws an exception. Your application must not generate an answer following such an exception.

**Limitations:** The registry's current credential is a shared operator token, not a per-service identity. Policy hashing is insertion-order compact JSON, not standardized JCS canonicalization; this implementation is compatible only with the present Node registry serializer. TLS is required outside loopback. No caching, signed receipts, rollback protection, distributed approval or policy refresh exists. This client is a development integration, not a production policy-distribution security boundary.

Next: canonical cross-language content hashing, service-scoped read credentials, signed bundles, bounded cache with expiry and monotonic version rollout, integration into Spring Boot auto-configuration.
