# QualityRag cross-language conformance

The JSON file `conformance/v0.1.json` defines fixed-clock, deterministic scenarios: independent corroboration, shared provenance, contradiction, missing, stale, unknown and future evidence.

Python and TypeScript execute all seven fixtures in CI. Java, Go, .NET, Rust, Kotlin, PHP, Ruby and Swift currently run native smoke/unit tests but **do not yet execute the shared fixture file**, so cross-language parity is not certified.

This is metadata consistency, not proof of source truth or independence. Subsequent milestone: implement shared fixture runners in all language SDKs, versioning every change in meaning and refusal behavior.
