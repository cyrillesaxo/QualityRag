# Language expansion

Ruby, PHP, Kotlin, Swift implement v0.1 evidence metadata gate with matching three-way verdict semantics. All source authority and origin values remain caller supplied.

Run Ruby: `ruby sdk/ruby/test/test_qualityrag.rb`. PHP: `php -d zend.assertions=1 -d assert.exception=1 sdk/php/test.php`. Kotlin: `cd sdk/kotlin && gradle test`. Swift: `cd sdk/swift && swift test`.

**Parity limitation:** Advanced semantic compiler, WitnessGraph and Wgap are still Python/TypeScript only. These four SDKs and Go/.NET/Rust provide the bounded metadata evaluator, not full QualityRag assurance. Package registries not published.
