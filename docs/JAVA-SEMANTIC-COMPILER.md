# Java ConstraintIR compiler

`io.qualityrag.SemanticCompiler` adds the bounded Python/TypeScript semantic compiler surface to Java 17:
`compile(JsonNode)` and `evaluate(JsonNode, JsonNode, Instant)`. It emits typed obligation metadata, witness origin dependency groups and Wgap reason codes.

The compiler is intentionally deterministic and **does not validate document contents, independent authority, actual source lineage, or the full APX semantic grammar**. No Spring Boot auto-configuration is included yet.

Run `cd sdk/java && mvn test`. Tests cover compile, independent origins, dependent sources, missing obligation, scope mismatch and contradiction. Cross-language semantic compiler golden equivalence is still required.
