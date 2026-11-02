# QualityRag for Php

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

## Prerequisites and onboarding

PHP 8.3; source is included directly, with no Composer package published. Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
php -d zend.assertions=1 -d assert.exception=1 sdk/php/test.php && php sdk/php/conformance.php
```

## API

`QualityRag\Gate::evaluate(array $pack,array $evidence,?DateTimeImmutable $asOf): array`.

## First decision

```php
require __DIR__ . "/sdk/php/src/QualityRag.php";
$pack = ["id"=>"demo","version"=>"1","requirements"=>[["id"=>"r","min_independent_sources"=>2]]];
$result = \QualityRag\Gate::evaluate($pack,[],new DateTimeImmutable("2026-11-02T10:05:00Z"));
echo $result["verdict"]; // INCONCLUSIVE
```

The empty evidence array does not satisfy two independent sources; the expected decision is `INCONCLUSIVE`. These snippets show API usage from the repository source tree; they are not package-registry installation commands. Import paths assume the corresponding local module/project is built or referenced in your application.

## Integration checklist

- Keep the PackSpec server-owned and versioned.
- Supply provenance and timestamps from a trusted collector; never infer independence from two matching URLs alone.
- Block or defer model generation on both `REFUSE` and `INCONCLUSIVE`.
- Record sanitized findings and test with `conformance/v0.1.json`.

## Compatibility

The base metadata gate is supported here. The advanced ConstraintIR/WitnessGraph/Wgap compiler is **not yet available** in this SDK. See [concepts](../concepts.md) for detailed semantics and limits.

## Help

If a run fails, consult [troubleshooting](../troubleshooting.md), then [support](../support.md). Include runtime version, sanitized inputs and exact result; never include confidential evidence in a public issue.
