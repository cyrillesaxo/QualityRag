package io.qualityrag
import com.fasterxml.jackson.databind.ObjectMapper
import java.nio.file.Path
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals

class APXPackExamplesTest {
 @Test fun allFifteenCases() {
  val fixture=ObjectMapper().readTree(Path.of("../../examples/apx-packspecs/fixtures.json").toFile())
  val at=Instant.parse(fixture["as_of"].asText())
  var count=0
  for(domain in fixture["scenarios"]) {
   val raw=domain["pack"]
   val pack=Pack(raw["id"].asText(),raw["version"].asText(),
     raw["requirements"].map{Requirement(it["id"].asText())})
   for(example in domain["cases"]) {
    val witnesses=example["evidence"].map { w -> Witness(
      w["id"].asText(),w["requirement_id"].asText(),w["origin"].asText(),
      w["source_ref"].asText(),w["status"].asText(),Instant.parse(w["observed_at"].asText())) }
    assertEquals(example["expected"].asText(),Gate.evaluate(pack,witnesses,at).verdict)
    count++
   }
  }
  assertEquals(15,count)
 }
}
