import Foundation

public struct Requirement { public let id:String; public let minIndependentSources:Int; public let maxAgeSeconds:TimeInterval?
 public init(_ id:String, minIndependentSources:Int=1,maxAgeSeconds:TimeInterval?=nil){self.id=id;self.minIndependentSources=minIndependentSources;self.maxAgeSeconds=maxAgeSeconds}}
public struct Pack {public let id:String;public let version:String;public let requirements:[Requirement]
 public init(_ id:String,_ version:String,_ requirements:[Requirement]){self.id=id;self.version=version;self.requirements=requirements}}
public struct Witness {public let id:String;public let requirementId:String;public let origin:String;public let sourceRef:String;public let status:String;public let observedAt:Date
 public init(_ id:String,_ requirementId:String,_ origin:String,_ sourceRef:String,_ status:String,_ observedAt:Date){self.id=id;self.requirementId=requirementId;self.origin=origin;self.sourceRef=sourceRef;self.status=status;self.observedAt=observedAt}}
public struct Finding {public let requirementId:String;public let verdict:String;public let independentSources:Int;public let reasons:[String]}
public struct Result {public let verdict:String;public let findings:[Finding]}
public enum Gate {
 /// Evaluates supplied metadata. Does not authenticate source claims.
 public static func evaluate(_ pack:Pack,_ evidence:[Witness],asOf:Date=Date()) -> Result {
  precondition(!pack.id.isEmpty && !pack.version.isEmpty && !pack.requirements.isEmpty)
  precondition(Set(pack.requirements.map{$0.id}).count == pack.requirements.count)
  let findings=pack.requirements.map { r -> Finding in
   precondition(!r.id.isEmpty && r.minIndependentSources>0 && (r.maxAgeSeconds == nil || r.maxAgeSeconds! >= 0))
   var origins=Set<String>();var reasons=Set<String>();var contradiction=false
   for w in evidence where w.requirementId == r.id {
    if w.id.isEmpty || w.origin.isEmpty || w.sourceRef.isEmpty || !["SUPPORTS","CONTRADICTS","UNKNOWN"].contains(w.status) {reasons.insert("INVALID_EVIDENCE");continue}
    let age=asOf.timeIntervalSince(w.observedAt)
    if age < 0 {reasons.insert("FUTURE_EVIDENCE");continue}
    if let max=r.maxAgeSeconds,age > max {reasons.insert("STALE_EVIDENCE");continue}
    switch w.status {case "CONTRADICTS":contradiction=true;case "SUPPORTS":origins.insert(w.origin);default:reasons.insert("UNKNOWN_EVIDENCE")}
   }
   let verdict=contradiction ? "REFUSE" : origins.count < r.minIndependentSources ? "INCONCLUSIVE" : "ADMIT"
   if contradiction {reasons.insert("CONTRADICTION")} else if origins.count < r.minIndependentSources {reasons.insert("INSUFFICIENT_INDEPENDENT_EVIDENCE")}
   return Finding(requirementId:r.id,verdict:verdict,independentSources:origins.count,reasons:reasons.sorted())
  }
  let verdict=findings.contains{$0.verdict=="REFUSE"} ? "REFUSE" : findings.contains{$0.verdict=="INCONCLUSIVE"} ? "INCONCLUSIVE" : "ADMIT"
  return Result(verdict:verdict,findings:findings)
 }
}
