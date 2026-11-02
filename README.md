# QualityRag

**A deterministic evidence-completeness gate for retrieval-augmented generation.**

[**Get started →**](docs/quickstart.md) · [**Browse all 10 SDK guides →**](docs/README.md#choose-your-sdk) · [**API concepts →**](docs/concepts.md) · [**Get help →**](docs/troubleshooting.md)

---

![QualityRag evidence governance flow](docs/assets/how-it-works.svg)

## Why QualityRag?

A retrieved passage can be accurate while the answer remains unsupported: a missing exception, unresolved scope, stale witness, or duplicated source may change the outcome.

QualityRag evaluates a **versioned PackSpec** against *caller-supplied evidence metadata* before an application calls an answer generator.

| Verdict | What it means |
| :--- | :--- |
| **ADMIT** | Submitted metadata meets declared requirements |
| **REFUSE** | Governing contradiction detected |
| **INCONCLUSIVE** | One or more evidence obligations remain unresolved |

> [!IMPORTANT]
> **ADMIT does not verify source truth, authority, or actual independence.** The public SDK is experimental and should not be represented as certified semantic assurance.

### What the three decisions mean

![ADMIT, REFUSE and INCONCLUSIVE illustrated](docs/assets/three-decisions.svg)

### A missing-exception failure

![Retrieved rule without its governing exception](docs/assets/hidden-exception.svg)

The missing exception must be **declared in PackSpec** for the current evaluator to detect it.

## Start building

| Your stack | Guide |
| :--- | :--- |
| Java / Spring Boot | [Java SDK](docs/languages/java.md) · [Spring Boot integration](docs/SPRING-BOOT.md) |
| Python | [Python SDK](docs/languages/python.md) |
| TypeScript / React | [TypeScript SDK](docs/languages/typescript.md) |
| Go · .NET · Rust · Kotlin | [Backend SDK directory](docs/README.md#choose-your-sdk) |
| PHP · Ruby · Swift | [Application SDK directory](docs/README.md#choose-your-sdk) |

```bash
# Clone and run the dependency-free Python gate tests
git clone https://github.com/cyrillesaxo/QualityRag.git
cd QualityRag
PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests
```

**[Full developer documentation →](docs/README.md)**

## Current capabilities

| Module | Status |
| :--- | :--- |
| Evidence metadata gate | 10 languages |
| Shared conformance suite | 10 languages |
| ConstraintIR · WitnessGraph · Wgap prototypes | Java / Python / TypeScript |
| Spring Boot answer gate | Implemented |
| Spring AI adapter | Under review in PR #9 |
| Complete APX D15, G1–G12, HCR, TERM and RCOC | Not yet ported |

No Maven Central, PyPI, npm, NuGet, crates.io, RubyGems, Packagist, or Swift package registry release is claimed. Build these experimental SDKs from repository source.

## Design and provenance

The public contract is inspired by private APX work including PackSpec, witness provenance, admission/refusal, evidence independence, and bounded semantic assurance. It deliberately does not publish private APX infrastructure, customer data, or credentials.

[Architecture](docs/ADR-0001-semantic-constraint-compiler.md) · [Roadmap](docs/ROADMAP.md) · [Security & support](docs/support.md) · [Apache-2.0 license](LICENSE)
