package io.qualityrag.spring;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class AnswerGateTest {
 private final ObjectMapper mapper=new ObjectMapper();
 private final Instant now=Instant.parse("2026-11-02T10:05:00Z");
 private final String pack="""
  {"id":"policy","version":"1","requirements":[{"id":"r","min_independent_sources":2,"scope":"GA","authority":"official"}]}
  """;
 private String w(String id,String origin,String status){
  return "{\"id\":\""+id+"\",\"requirement_id\":\"r\",\"origin\":\""+origin+"\",\"source_ref\":\"doc:"+id+"\",\"scope\":\"GA\",\"authority\":\"official\",\"observed_at\":\"2026-11-02T10:00:00Z\",\"status\":\""+status+"\"}";
 }
 @Test void neverGeneratesOnIncompleteEvidence() throws Exception {
  var calls=new AtomicInteger();
  var outcome=new AnswerGate().generate(mapper.readTree(pack),mapper.readTree("["+w("a","same","SUPPORTS")+","+w("b","same","SUPPORTS")+"]"),now,()->{calls.incrementAndGet();return "unsupported";});
  assertEquals("INCONCLUSIVE",outcome.verdict());assertNull(outcome.answer());assertEquals(0,calls.get());
  assertEquals(1,outcome.receipt().path("wgap").size());
 }
 @Test void neverGeneratesOnContradiction() throws Exception {
  var calls=new AtomicInteger();
  var outcome=new AnswerGate().generate(mapper.readTree(pack),mapper.readTree("["+w("a","A","SUPPORTS")+","+w("b","B","CONTRADICTS")+"]"),now,()->{calls.incrementAndGet();return "unsupported";});
  assertEquals("REFUSE",outcome.verdict());assertEquals(0,calls.get());
 }
 @Test void generatesOnceOnAdmission() throws Exception {
  var calls=new AtomicInteger();
  var outcome=new AnswerGate().generate(mapper.readTree(pack),mapper.readTree("["+w("a","A","SUPPORTS")+","+w("b","B","SUPPORTS")+"]"),now,()->{calls.incrementAndGet();return "bounded";});
  assertEquals("ADMIT",outcome.verdict());assertEquals("bounded",outcome.answer());assertEquals(1,calls.get());
 }
 @Test void invalidPackFailsClosed() throws Exception {
  var calls=new AtomicInteger();
  assertThrows(IllegalArgumentException.class,()->new AnswerGate().generate(mapper.readTree("{}"),mapper.readTree("[]"),now,()->{calls.incrementAndGet();return "bad";}));
  assertEquals(0,calls.get());
 }
}
