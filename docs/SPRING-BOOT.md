# Spring Boot answer gate — experimental

This module provides a server-side `AnswerGate` and Spring Boot 3 auto-configuration. It depends on the adjacent Java SDK, and is not yet on Maven Central.

```java
Outcome<String> outcome = answerGate.generate(packSpec, trustedEvidenceMetadata, Instant.now(),
    () -> ragService.generateAnswer(question));
if (!outcome.admitted()) {
    // Return safe response with unresolved constraints, not the RAG answer.
}
```

The generator is **never called** for REFUSE/INCONCLUSIVE or invalid PackSpec. The service deliberately requires application-owned policy and trusted evidence metadata. ADMIT proves only matching metadata under declared constraints, not ground truth or authenticity. Do not put secrets/PHI into public receipts.

Build in order: `mvn -f sdk/java/pom.xml install -DskipTests`, then `mvn -f sdk/spring-boot/pom.xml test`.

Next: real LangChain4j/Spring AI adapters, authenticated policy registry, protected evidence collectors, explicit controller response mapping and common semantic conformance fixtures.
