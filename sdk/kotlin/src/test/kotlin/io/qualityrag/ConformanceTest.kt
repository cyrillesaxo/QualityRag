package io.qualityrag
import kotlin.test.Test
import kotlin.test.assertEquals
import java.io.File
import java.time.Instant
import groovy.json.JsonSlurper
class ConformanceTest {
 @Test fun sharedFixtures() {
  val suite=JsonSlurper().parse(File("../../conformance/v0.1.json")) as Map<*,*>
  val now=Instant.parse(suite["as_of"] as String)
  val pack=Pack("conformance","1",listOf(Requirement("r",2,3600)))
  for(case in suite["cases"] as List<*>) {
   val item=case as Map<*,*>
   val rows=(item["evidence"] as List<*>).map { value ->
    val x=value as List<*>
    Witness(x[0] as String,"r",x[1] as String,"doc:"+x[0],x[2] as String,Instant.parse(if(x.size>3)x[3] as String else "2026-11-02T10:00:00Z"))
   }
   val out=Gate.evaluate(pack,rows,now)
   assertEquals(item["verdict"],out.verdict,item["name"] as String)
   assertEquals(item["reasons"],out.findings[0].reasons,item["name"] as String)
  }
 }
}
