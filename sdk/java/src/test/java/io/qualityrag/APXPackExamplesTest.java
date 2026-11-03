package io.qualityrag;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

/** Same 12 source-grounded training projections used by every SDK. */
class APXPackExamplesTest {
 @Test void sharedFixtures() throws Exception {
  var fixtures = Path.of("examples/apx-packspecs/fixtures.json");
  if (!java.nio.file.Files.isRegularFile(fixtures))
    fixtures = Path.of("../../examples/apx-packspecs/fixtures.json");
  var root = new ObjectMapper().readTree(fixtures.toFile());
  var asOf=Instant.parse(root.path("as_of").asText());
  int count=0;
  for(var domain:root.path("scenarios"))for(var item:domain.path("cases")) {
    var outcome=QualityRag.evaluate(domain.path("pack"),item.path("evidence"),asOf);
    assertEquals(item.path("expected").asText(),outcome.path("verdict").asText(),
      domain.path("id").asText()+"/"+item.path("id").asText());
    count++;
  }
  assertEquals(15,count);
 }
}
