package io.qualityrag;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class SemanticCompilerTest {
 private static final ObjectMapper M=new ObjectMapper();
 private static final Instant NOW=Instant.parse("2026-11-02T10:05:00Z");
 private static final String POLICY="""
 {"id":"policy","version":"1","requirements":[{"id":"eligibility","min_independent_sources":2,"scope":"GA","authority":"official","max_age_seconds":3600}]}
 """;
 private static JsonNode witness(String id,String origin,String status) throws Exception {
  return M.readTree("{\"id\":\""+id+"\",\"requirement_id\":\"eligibility\",\"origin\":\""+origin+"\",\"source_ref\":\"doc:"+id+"\",\"scope\":\"GA\",\"authority\":\"official\",\"observed_at\":\"2026-11-02T10:00:00Z\",\"status\":\""+status+"\"}");
 }
 private JsonNode assess(JsonNode... witnesses) throws Exception {return SemanticCompiler.evaluate(M.readTree(POLICY),M.valueToTree(witnesses),NOW);}
 @Test void compilesAndAdmits() throws Exception {
  var result=assess(witness("a","A","SUPPORTS"),witness("b","B","SUPPORTS"));
  assertEquals("ADMIT",result.path("verdict").asText());
  assertEquals("GA",result.path("constraint_ir").get(0).path("required_scope").asText());
  assertTrue(result.path("wgap").isEmpty());
 }
 @Test void tracksSharedOriginsAndGap() throws Exception {
  var result=assess(witness("a","A","SUPPORTS"),witness("b","A","SUPPORTS"));
  assertEquals("INCONCLUSIVE",result.path("verdict").asText());
  assertEquals(1,result.path("wgap").get(0).path("missing_sources").asInt());
  assertEquals(1,result.path("witness_graph").path("dependent_groups").size());
 }
 @Test void contradictionRefuses() throws Exception {
  assertEquals("REFUSE",assess(witness("a","A","SUPPORTS"),witness("b","B","CONTRADICTS")).path("verdict").asText());
 }
 @Test void scopeMismatchInconclusive() throws Exception {
  var one=(com.fasterxml.jackson.databind.node.ObjectNode)witness("a","A","SUPPORTS");
  one.put("scope","FL");
  var result=assess(one,witness("b","B","SUPPORTS"));
  assertEquals("INCONCLUSIVE",result.path("verdict").asText());
  assertEquals("SCOPE_MISMATCH",result.path("findings").get(0).path("reasons").get(1).asText());
 }
}
