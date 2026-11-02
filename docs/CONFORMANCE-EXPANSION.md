# Expanded executable conformance

This PR adds shared conformance file runners for Go, C#/.NET, Ruby and PHP, in addition to the existing Python and TypeScript runners. Each reads `conformance/v0.1.json`, checks the overall verdict and exact sorted reason codes for seven cases.

The remaining Java, Rust, Kotlin and Swift engines still have native tests rather than shared JSON fixture runners. Advanced semantic compiler parity remains a separate project.

All fixtures test caller-supplied evidence metadata, not evidence authenticity.
