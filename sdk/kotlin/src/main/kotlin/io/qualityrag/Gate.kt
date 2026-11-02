package io.qualityrag

import java.time.Instant

data class Requirement(val id:String,val minIndependentSources:Int=1,val maxAgeSeconds:Long?=null)
data class Pack(val id:String,val version:String,val requirements:List<Requirement>)
data class Witness(val id:String,val requirementId:String,val origin:String,val sourceRef:String,val status:String,val observedAt:Instant)
data class Finding(val requirementId:String,val verdict:String,val independentSources:Int,val reasons:List<String>)
data class Result(val verdict:String,val findings:List<Finding>)

/** Caller-provided metadata, not proof that source claims are authentic. */
object Gate {
 fun evaluate(pack:Pack,evidence:List<Witness>,asOf:Instant=Instant.now()):Result {
  require(pack.id.isNotBlank() && pack.version.isNotBlank() && pack.requirements.isNotEmpty())
  require(pack.requirements.map{it.id}.distinct().size==pack.requirements.size)
  val findings=pack.requirements.map { req ->
   require(req.id.isNotBlank()&&req.minIndependentSources>0&&(req.maxAgeSeconds==null||req.maxAgeSeconds>=0))
   val origins=mutableSetOf<String>();val reasons=sortedSetOf<String>();var contradiction=false
   for(w in evidence.filter{it.requirementId==req.id}) {
    if(w.id.isBlank()||w.origin.isBlank()||w.sourceRef.isBlank()||w.status !in setOf("SUPPORTS","CONTRADICTS","UNKNOWN")) {reasons.add("INVALID_EVIDENCE");continue}
    if(w.observedAt>asOf) {reasons.add("FUTURE_EVIDENCE");continue}
    if(req.maxAgeSeconds!=null&&java.time.Duration.between(w.observedAt,asOf).toMillis()>req.maxAgeSeconds*1000){reasons.add("STALE_EVIDENCE");continue}
    when(w.status){"CONTRADICTS"->contradiction=true;"SUPPORTS"->origins.add(w.origin);else->reasons.add("UNKNOWN_EVIDENCE")}
   }
   val verdict=when {contradiction->"REFUSE";origins.size<req.minIndependentSources->"INCONCLUSIVE";else->"ADMIT"}
   if(contradiction) reasons.add("CONTRADICTION") else if(origins.size<req.minIndependentSources) reasons.add("INSUFFICIENT_INDEPENDENT_EVIDENCE")
   Finding(req.id,verdict,origins.size,reasons.toList())
  }
  return Result(when{findings.any{it.verdict=="REFUSE"}->"REFUSE";findings.any{it.verdict=="INCONCLUSIVE"}->"INCONCLUSIVE";else->"ADMIT"},findings)
 }
}
