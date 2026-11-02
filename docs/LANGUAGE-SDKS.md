# Language SDK coverage

Core metadata gate: Java 17, Python, TypeScript, Go, C#/.NET 8, Rust.

The additional Go, C#, Rust implementations expose the conservative original v0.1 gate (independent origin counts, freshness, contradictions). The advanced ConstraintIR/WitnessGraph/Wgap compiler currently exists only in Python/TypeScript. **Do not claim full parity.**

All decisions are based on caller-provided metadata; distinct origin strings do not establish actual source independence.

## Local validation
- Go: `cd sdk/go && go test ./...`
- .NET: `dotnet run --project sdk/csharp/QualityRag.Smoke`
- Rust: `cd sdk/rust && cargo test`

Planned next: JSON shared conformance vectors, extended compiler implementation for every language, adapters and release packaging after security review.
