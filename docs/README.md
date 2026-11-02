# QualityRag documentation

Start here: **[Quickstart](quickstart.md)** → **[Choose an SDK](#language-guides)** → **[Policy & decision reference](concepts.md)** → **[Troubleshooting](troubleshooting.md)**.

## Language guides

| SDK | Guide | Run tests |
|---|---|---|
| Java 17 | [Java](languages/java.md) | `mvn -f sdk/java/pom.xml test` |
| Python 3 | [Python](languages/python.md) | `PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests` |
| TypeScript / React | [TypeScript](languages/typescript.md) | `cd sdk/typescript && npm install && npm test` |
| Go 1.22 | [Go](languages/go.md) | `cd sdk/go && go test ./...` |
| C# / .NET 8 | [C#](languages/csharp.md) | `dotnet run --project sdk/csharp/QualityRag.Smoke` |
| Rust | [Rust](languages/rust.md) | `cd sdk/rust && cargo test` |
| Kotlin | [Kotlin](languages/kotlin.md) | `cd sdk/kotlin && gradle test` |
| PHP 8.3 | [PHP](languages/php.md) | `php -d zend.assertions=1 -d assert.exception=1 sdk/php/test.php` |
| Ruby 3.3 | [Ruby](languages/ruby.md) | `ruby sdk/ruby/test/test_qualityrag.rb` |
| Swift 5.9 | [Swift](languages/swift.md) | `cd sdk/swift && swift test` |

## Important limitations

The repository contains **source-built experimental SDKs**, not verified Maven Central, PyPI, npm, NuGet, crates.io, RubyGems, Packagist or Swift registry releases. The base v0.1 evidence metadata gate exists in all 10 languages. Extended ConstraintIR, WitnessGraph and Wgap currently exist in Java, Python and TypeScript, not all 10. Spring Boot starter is under `sdk/spring-boot`; Spring AI integration is under review in PR #9 as of this documentation change.

`ADMIT` means submitted metadata meets declared constraints. It does **not** certify source truth or source independence. Never use the browser as the authoritative enforcement boundary.

## More help

- [Concepts & API contract](concepts.md)
- [Troubleshooting / FAQ](troubleshooting.md)
- [Support and security](support.md)
- [Conformance tests](CONFORMANCE.md)
- [Spring Boot integration](SPRING-BOOT.md)
- [Java semantic compiler](JAVA-SEMANTIC-COMPILER.md)
- [Architecture ADR](ADR-0001-semantic-constraint-compiler.md)
