# Choose your PackSpec source: internal, property, file or Studio

QualityRag keeps **one evaluation contract** while allowing developers to choose **where the PackSpec lives**. In Java, use `PackSpecSource` to select an explicit authority. The rest of the application calls `source.load()` then `QualityRag.evaluate(...)` or `SemanticCompiler.evaluate(...)`.

| Mode | Authority | Best for | Trade-off |
| :--- | :--- | :--- | :--- |
| `internal` | Java application code | Local tests, embedded policies | Requires application release for edits |
| `property` | JSON supplied by configuration | Containers and deployments with config injection | Handle escaping and length limits |
| `file` | JSON document mounted on the host/container | GitOps / Kubernetes ConfigMap or mounted file | Protect file and coordinate version changes |
| `studio` | QualityRag Studio registry service/environment binding | Shared governance, approval/version control | Requires registry authentication, network, and integrity controls |

## Example PackSpec

```json
{
  "id": "eu-payments-recovery",
  "version": "1",
  "requirements": [
    {"id": "recovery-procedure"},
    {"id": "eu-screening-control"}
  ]
}
```

## Java usage

```java
// INTERNAL: application supplies an already-parsed policy.
PackSpecSource internal = PackSpecSource.internal(pack);

// PROPERTY: JSON string comes from deployment configuration.
PackSpecSource property = PackSpecSource.property(System.getenv("QUALITYRAG_PACKSPEC_JSON"));

// FILE: mount a policy at an explicit location.
PackSpecSource external = PackSpecSource.file(Path.of("/etc/qualityrag/policy.json"));

// STUDIO: fetch policy pinned by registered service and environment.
PackSpecSource studio = PackSpecSource.studio(
    URI.create("http://127.0.0.1:5055"), // loopback dev only; HTTPS otherwise
    System.getenv("QUALITYRAG_REGISTRY_TOKEN"),
    "claims-api", "dev"
);

// Choose ONE; do not fall back silently if the selected mode fails.
var receipt = SemanticCompiler.evaluate(studio.load(), evidence, Instant.now());
```

## Unified configuration (Java Properties)

```properties
qualityrag.packspec.source=file
qualityrag.packspec.path=/etc/qualityrag/policy.json
```

For inline JSON:

```properties
qualityrag.packspec.source=property
qualityrag.packspec.json={"id":"eu-payments-recovery","version":"1","requirements":[{"id":"recovery-procedure"},{"id":"eu-screening-control"}]}
```

For QualityRag Studio:

```properties
qualityrag.packspec.source=studio
qualityrag.registry.url=https://registry.example.com
qualityrag.registry.token=SET_BY_SECRET_MANAGER
qualityrag.service-id=claims-api
qualityrag.environment=production
```

Pass these into `PackSpecSource.fromProperties(props, internalPack)`. An explicit `internal` mode uses the `internalPack` argument; a missing mode is an error. Properties are **illustrative names interpreted by this Java factory**, not automatically loaded by Spring Boot auto-configuration. Do not check a real registry token into a properties file.

## Enforcement contract

1. Only one configured policy source is authoritative. No automatic fallback from Studio to a weaker embedded policy.
2. Reject missing, invalid or conflicting policy definitions before generating an answer.
3. The `studio` client requires HTTPS except localhost, verifies an approved envelope, service/environment identity, and a SHA-256 digest. The digest is **not a digital signature**.
4. The local registry uses a shared development token. Production requires per-service credentials, signed canonical bundles, rollback protection, and expiry.
5. `load()` runs on demand. This initial implementation does not promise caching, background refresh, or Spring Boot auto-wiring.

**Training scenario:** [Enterprise document ingestion lab](../examples/enterprise-rag/REAL-DOCUMENTS.md) illustrates why the governing obligation should be declared regardless of its policy location. All modes have the same core metadata-gate limitations.


## Python source selection (experimental)

```python
from qualityrag import evaluate
from qualityrag.sources import from_properties

config = {
    "qualityrag.packspec.source": "file",
    "qualityrag.packspec.path": "/etc/qualityrag/policy.json",
}
load_policy = from_properties(config)
result = evaluate(load_policy(), retrieved_evidence, as_of="2026-11-02T10:05:00Z")
if result["verdict"] != "ADMIT":
    # Skip model invocation: the required evidence is incomplete.
    ...
```

Select `internal`, `property`, `file` or `studio` with the same keys used by Java. In Studio mode, use a server-held bearer token and HTTPS outside loopback. A v0.1 registry digest detects mutation in transit but is **not a signature**.

## TypeScript source selection (experimental)

```typescript
import { packSpecSource } from "@qualityrag/sdk/dist/sources.js";

const load = packSpecSource({
  mode: "file",
  path: "/etc/qualityrag/policy.json",
  // Server-side adapter; do not use in browser code.
  readFile: async path => (await import("node:fs/promises")).readFile(path, "utf8")
});
const policy = await load();
// Use evaluate(policy, evidence, now) and only generate on ADMIT.
```

For Studio, use `mode: "studio"` with `registryUrl`, `registryToken`, `serviceId` and `environment`. Keep operator credentials **server-side**. For browser environments supply only vetted policies from your application backend; never expose the registry's shared development token. TypeScript file loading deliberately uses an application-injected readFile adapter, keeping the SDK platform-neutral.


## Seven additional SDKs

The explicit source-selection pattern is now also available in **Go, C#, Rust, Kotlin, PHP, Ruby and Swift**. These adapters expose the same four *logical* sources: application-owned PackSpec, inline JSON configuration, mounted JSON file, and Studio-approved registry binding.

| SDK | API | Studio transport |
| :--- | :--- | :--- |
| Go | `InternalPackSource`, `PropertyPackSource`, `FilePackSource`, `StudioPackSource`, `PackSourceFromProperties` | `net/http`, context-bound call |
| C# | `PackSpecSources.Internal/Property/File/Studio/FromProperties` | `HttpClient` async |
| Rust | `qualityrag::sources::{internal,property,file,studio,from_properties}` | Application-injected `HttpGet` callback |
| Kotlin | `PackSpecSources.internal/property/file/studio/fromProperties` | JDK `HttpClient` |
| PHP | `PackSpecSource::internal/property/file/studio/fromProperties` | PHP HTTP stream, injectable callback |
| Ruby | `QualityRag::Sources.internal/property/file/studio/from_properties` | Net::HTTP, injectable callback |
| Swift | `PackSpecSources.internalPolicy/property/file/studio` | async `URLSession` |

**Intended logic for every language:**

```text
Explicit source configuration
           ↓
Load the selected PackSpec or throw (no fallback)
           ↓
Validate declared requirements
           ↓
Evaluate the RAG witnesses with the existing SDK gate
           ↓
Only on ADMIT: invoke the answer-generating model
```

The Studio registry currently creates SHA-256 fingerprints over Node `JSON.stringify(policy)`. Adapters check this fingerprint when available; a digest is **not** a signature or independent authorization. Schema-different JSON serializers, custom field ordering, and non-ASCII serialization can require a future canonical policy envelope. Do not silently bypass integrity checks to work around a mismatch.

Rust requires a caller-provided HTTP transport rather than bundling an HTTP client. Swift uses CryptoKit and currently supports Apple platforms as declared in its package manifest. None of these sources adds caching, signed policies, per-service registry credentials or automatic discovery of undeclared constraints.

**Attribution:** Cyrille Eloundou — [APX](https://apx.guide/), PackSpec and semantic governance concepts.

