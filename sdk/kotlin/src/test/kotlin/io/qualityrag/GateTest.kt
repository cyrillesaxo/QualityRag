package io.qualityrag
import kotlin.test.Test
import kotlin.test.assertEquals
import java.time.Instant
class GateTest {
 @Test fun decisions() {
  val now=Instant.parse("2026-11-02T10:05:00Z")
  val p=Pack("p","1",listOf(Requirement("r",2)))
  val a=Witness("a","r","A","doc:a","SUPPORTS",now.minusSeconds(300))
  val b=a.copy(id="b",origin="B")
  assertEquals("ADMIT",Gate.evaluate(p,listOf(a,b),now).verdict)
  assertEquals("INCONCLUSIVE",Gate.evaluate(p,listOf(a,b.copy(origin="A")),now).verdict)
  assertEquals("REFUSE",Gate.evaluate(p,listOf(a,b.copy(status="CONTRADICTS")),now).verdict)
 }
}
