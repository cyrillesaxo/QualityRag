package io.qualityrag.spring;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.qualityrag.PackSpecSource;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ConfiguredAnswerGateTest {
 private final ObjectMapper json=new ObjectMapper();
 private final Instant now=Instant.parse("2026-11-02T10:05:00Z");
 @Test void missingEuControlMustNotGenerate() throws Exception {
  var source=PackSpecSource.property("""
   {"id":"eu-recovery","version":"1","requirements":[{"id":"recovery-procedure"},{"id":"eu-screening-control"}]}
   """);
  var evidence=json.readTree("""
   [{"id":"chunk-74","requirement_id":"recovery-procedure","origin":"ops-handbook",
     "source_ref":"operations.pdf#page=74","status":"SUPPORTS","observed_at":"2026-11-02T10:00:00Z"}]
   """);
  var called=new AtomicInteger();
  var outcome=new ConfiguredAnswerGate(source).generate(evidence,now,()->{called.incrementAndGet();return "Yes, restart";});
  assertEquals("INCONCLUSIVE",outcome.verdict());
  assertEquals(0,called.get());
  assertNull(outcome.answer());
 }
 @Test void missingFileFailsWithoutCallingGenerator() throws Exception {
  var called=new AtomicInteger();
  var gate=new ConfiguredAnswerGate(PackSpecSource.file(java.nio.file.Path.of("/missing-qualityrag-policy-"+System.nanoTime())));
  assertThrows(IllegalStateException.class,()->gate.generate(json.readTree("[]"),now,()->{called.incrementAndGet();return "unsafe";}));
  assertEquals(0,called.get());
 }
}
