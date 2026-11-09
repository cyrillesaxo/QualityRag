# QualityRag for Php

[← Documentation home](../README.md) · [Quickstart](../quickstart.md) · [Troubleshooting](../troubleshooting.md)

> **SDK status:** Experimental · Source-built · Base evidence metadata gate available


## 1. Prerequisites & setup

PHP 8.3; source is included directly, with no Composer package published. Clone the repo and work from its root unless noted. This source SDK is **not published to a package registry**.

```sh
php -d zend.assertions=1 -d assert.exception=1 sdk/php/test.php && php sdk/php/conformance.php
```

## 2. API reference

`QualityRag\Gate::evaluate(array $pack,array $evidence,?DateTimeImmutable $asOf): array`.

## 3. Example: incomplete retrieval from a large PDF corpus

An enterprise RAG search retrieves page 74 of a **Payments Operations Handbook** but misses page 187 of a governing **EU Financial Controls Annex**. The PackSpec declares both evidence obligations. Only the general procedure has a supporting witness.

```php
<?php
require "sdk/php/src/QualityRag.php";
$pack = ["id"=>"eu-recovery","version"=>"1","requirements"=>[
  ["id"=>"recovery-procedure"],["id"=>"eu-screening-control"]]];
$evidence = [[
  "id"=>"pdf-74","requirement_id"=>"recovery-procedure",
  "origin"=>"operations-handbook","source_ref"=>"operations.pdf#page=74",
  "status"=>"SUPPORTS","observed_at"=>"2026-11-02T10:00:00Z"
]];
$result = \QualityRag\Gate::evaluate($pack,$evidence,
    new DateTimeImmutable("2026-11-02T10:05:00Z"));
echo $result["verdict"]; // INCONCLUSIVE
```

**Expected verdict:** `INCONCLUSIVE`. The application must not invoke its answer-generating model until the missing obligation has been resolved. This is the v0.1 **metadata gate**; it does not retrieve or parse PDFs. See [enterprise training](../TRAINING.md) and [document ingestion](../../examples/enterprise-rag/REAL-DOCUMENTS.md).

## 4. Production integration checklist

- Keep the PackSpec server-owned and versioned.
- Supply provenance and timestamps from a trusted collector; never infer independence from two matching URLs alone.
- Block or defer model generation on both `REFUSE` and `INCONCLUSIVE`.
- Record sanitized findings and test with `conformance/v0.1.json`.

## 5. Compatibility & limitations

The base metadata gate is supported here. The advanced ConstraintIR/WitnessGraph/Wgap compiler is **not yet available** in this SDK. See [concepts](../concepts.md) for detailed semantics and limits.

## 6. Help & troubleshooting

If a run fails, consult [troubleshooting](../troubleshooting.md), then [support](../support.md). Include runtime version, sanitized inputs and exact result; never include confidential evidence in a public issue.

---

**Continue reading:** [All language SDKs](../README.md#choose-your-sdk) · [PackSpec reference](../concepts.md) · [Report an issue](https://github.com/cyrillesaxo/QualityRag/issues)
