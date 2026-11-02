package io.qualityrag;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ConformanceTest {
 @Test void sharedFixtures() throws Exception {
  ObjectMapper mapper = new ObjectMapper();
  JsonNode suite=mapper.readTree(Files.readString(Path.of("../../conformance/v0.1.json")));
  Instant now=Instant.parse(suite.path("as_of").asText());
  for(JsonNode c:suite.path("cases")){
   List<com.fasterxml.jackson.databind.node.ObjectNode> evidence=new ArrayList<>();
   for(JsonNode row:c.path("evidence")){
    var witness=mapper.createObjectNode();
    witness.put("id",row.get(0).asText());
    witness.put("origin",row.get(1).asText());
    witness.put("status",row.get(2).asText());
    witness.put("source_ref","doc:"+row.get(0).asText());
    witness.put("requirement_id","r");
    witness.put("observed_at",row.size()>3?row.get(3).asText():"2026-11-02T10:00:00Z");
    evidence.add(witness);
   }
   JsonNode result=QualityRag.evaluate(suite.path("pack"),mapper.valueToTree(evidence),now);
   assertEquals(c.path("verdict").asText(),result.path("verdict").asText(),c.path("name").asText());
   assertEquals(c.path("reasons"),result.path("findings").get(0).path("reasons"),c.path("name").asText());
  }
 }
}
