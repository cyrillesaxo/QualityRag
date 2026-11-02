package io.qualityrag;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class QualityRagTest {
  private final ObjectMapper json = new ObjectMapper();
  private final Instant now = Instant.parse("2026-11-02T10:05:00Z");
  private final String pack = """
      {"id":"p","version":"1","requirements":[{"id":"r","min_independent_sources":2,"max_age_seconds":3600}]}
      """;
  private String witness(String id,String origin,String status) {
    return "{\"id\":\""+id+"\",\"origin\":\""+origin+"\",\"requirement_id\":\"r\",\"source_ref\":\"source:"+id+"\",\"status\":\""+status+"\",\"observed_at\":\"2026-11-02T10:00:00Z\"}";
  }
  private String verdict(String... witnesses) throws Exception {
    JsonNode p = json.readTree(pack), e = json.readTree("["+String.join(",",witnesses)+"]");
    return QualityRag.evaluate(p,e,now).path("verdict").asText();
  }
  @Test void admitsIndependentEvidence() throws Exception {
    assertEquals("ADMIT", verdict(witness("a","A","SUPPORTS"),witness("b","B","SUPPORTS")));
  }
  @Test void sharedOriginIsInconclusive() throws Exception {
    assertEquals("INCONCLUSIVE", verdict(witness("a","A","SUPPORTS"),witness("b","A","SUPPORTS")));
  }
  @Test void contradictionsRefuse() throws Exception {
    assertEquals("REFUSE", verdict(witness("a","A","SUPPORTS"),witness("b","B","SUPPORTS"),witness("c","C","CONTRADICTS")));
  }
}
