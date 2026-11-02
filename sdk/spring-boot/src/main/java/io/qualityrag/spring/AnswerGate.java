package io.qualityrag.spring;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.qualityrag.SemanticCompiler;
import java.time.Instant;
import java.util.Objects;
import java.util.function.Supplier;

/** Server-side gate: the generator is never called unless the evidence gate admits. */
public final class AnswerGate {
 public record Outcome<T>(String verdict, T answer, ObjectNode receipt) {
  public boolean admitted(){return "ADMIT".equals(verdict);}
 }
 public <T> Outcome<T> generate(JsonNode pack, JsonNode evidence, Instant asOf, Supplier<T> generator) {
  Objects.requireNonNull(generator, "generator");
  // Configuration errors propagate; they must never fall back to answer generation.
  ObjectNode receipt=SemanticCompiler.evaluate(pack,evidence,asOf);
  String verdict=receipt.path("verdict").asText();
  if(!"ADMIT".equals(verdict))return new Outcome<>(verdict,null,receipt);
  T answer=generator.get();
  return new Outcome<>(verdict,answer,receipt);
 }
}
