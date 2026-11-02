# Help, FAQ and troubleshooting

**Why did my result say INCONCLUSIVE?** Check `findings[].reasons`. Common causes: too few distinct declared origins, stale timestamps, missing requirements, unsupported witness status, and future timestamps. On Java/Python/TypeScript extended compiler, inspect `wgap`.

**Why do two search results count as one?** Both share the same `origin`. Copies of a source are not independent corroboration.

**Why does the SDK ADMIT a false statement?** The metadata gate validates submitted labels and conditions; it cannot inspect source truth. Use trusted collection, independent source verification, and post-generation checks for your risk level.

**Why is there no `pip install qualityrag` / `npm install @qualityrag/sdk`?** The packages have not been published. Build/run from the cloned repository instead. The TypeScript package currently declares `private: true`.

**Why is my package not found in Maven, NuGet, Packagist or crates.io?** Registry publishing has not happened; use the in-repository Maven, Gradle, Cargo, SwiftPM, .NET and direct-source workflows shown in each guide.

**My tests fail due to a missing runtime.** Install the required Java 17, Node 22, Python 3, Go 1.22, .NET 8, PHP 8.3, Ruby 3.3, Swift 5.9 or an installed Gradle compatible with Kotlin 2.0.21. See the pinned CI workflow in `.github/workflows` for baseline versions.

**Does React enforce governance?** No. Its hook is for display and local evaluation. Enforce admission again on a trusted server.

**Can I use my own PackSpec?** Yes. Start with the v0.1 JSON schema; the extended compiler also accepts scope and authority labels. Untrusted policy changes must not be accepted from a client.

**Can INCONCLUSIVE trigger automatic retrieval?** Not in the base SDK. Wgap identifies missing obligations; HCR/recovery planning is not yet ported.

**How can I report a bug?** See [support](support.md). Include language, runtime version, sanitized policy/evidence and the exact expected versus actual decision. Never paste secrets or sensitive documents in a public issue.
