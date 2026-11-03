# Spring Boot PackSpec source configuration

Use QualityRag's **configured answer gate** to load policy before every model invocation. The opt-in auto-configuration accepts the same source modes as the Java SDK: `internal`, `property`, `file`, and `studio`. It is enabled only when `qualityrag.packspec.source` is set. The original request-supplied `AnswerGate` remains available without the new configuration.

## Spring Boot 3 example

```properties
qualityrag.packspec.source=file
qualityrag.packspec.path=/etc/qualityrag/eu-recovery.json
```

Or configure the Studio development registry:

```properties
qualityrag.packspec.source=studio
qualityrag.registry.url=http://127.0.0.1:5055
qualityrag.registry.token=${QUALITYRAG_REGISTRY_TOKEN}
qualityrag.service-id=payments-api
qualityrag.environment=dev
```

Or the in-process property:

```properties
qualityrag.packspec.source=property
qualityrag.packspec.json={"id":"eu-recovery","version":"1","requirements":[{"id":"recovery-procedure"},{"id":"eu-screening-control"}]}
```

For application-owned internal PackSpecs, set `qualityrag.packspec.source=internal` and define a `PackSpecSource` bean explicitly:

```java
@Bean
PackSpecSource euRecoveryPolicy(ObjectMapper json) throws Exception {
    return PackSpecSource.internal(json.readTree(
        "{\"id\":\"eu-recovery\",\"version\":\"1\",\"requirements\":[{\"id\":\"recovery-procedure\"},{\"id\":\"eu-screening-control\"}]}"
    ));
}
```

The Spring Boot auto-configuration creates a `ConfiguredAnswerGate` bean, unless the application defines one. It resolves the selected PackSpec, evaluates evidence and only invokes the supplier on `ADMIT`:

```java
@Autowired ConfiguredAnswerGate gate;

var result = gate.generate(evidence, Instant.now(), () -> chatClient.call(prompt));
if (!result.admitted()) {
    // Return an evidence-completeness response; do not bypass the gate.
}
```

**Failure contract:** No fallback. A missing file or unavailable Studio registry throws; the model supplier is not invoked. Studio mode's registry uses a shared development token and has no production-grade service authentication, cache or signatures. See [PackSpec source selection](PACKSPEC-SOURCES.md).

Reference: Cyrille Eloundou, [APX](https://apx.guide/), for PackSpec/semantic governance concepts.
