package io.qualityrag.spring;

import com.fasterxml.jackson.databind.JsonNode;
import io.qualityrag.PackSpecSource;
import java.time.Instant;
import java.util.Objects;
import java.util.function.Supplier;

/** Loads the authoritative PackSpec before each attempted generation. */
public final class ConfiguredAnswerGate {
 private final PackSpecSource source;
 private final AnswerGate gate = new AnswerGate();

 public ConfiguredAnswerGate(PackSpecSource source) {
  this.source = Objects.requireNonNull(source,"source");
 }

 /** Errors loading policy propagate and NEVER invoke the answer supplier. */
 public <T> AnswerGate.Outcome<T> generate(JsonNode evidence, Instant asOf, Supplier<T> generator) {
  Objects.requireNonNull(generator,"generator");
  JsonNode pack = source.load(); // fail closed: no fallback on missing or invalid policy
  return gate.generate(pack,evidence,asOf,generator);
 }
}
