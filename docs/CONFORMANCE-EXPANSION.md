# Cross-language conformance runners

All ten SDKs now have test runners targeting `conformance/v0.1.json`:

Java, Python, TypeScript, Go, .NET, Rust, Kotlin, PHP, Ruby, Swift.

The fixed-clock suite checks exact overall verdict and sorted finding reasons for independent, duplicate, contradictory, missing, stale, unknown and future evidence. Every language must pass its CI job before parity is described as verified.

**Scope**: This suite covers the v0.1 metadata gate only. Advanced ConstraintIR, WitnessGraph and Wgap have not been ported to all SDKs. Caller-provided origin identifiers do not verify actual source independence.
