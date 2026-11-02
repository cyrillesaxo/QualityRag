import XCTest
@testable import QualityRag
final class GateTests:XCTestCase {
 func testThreeDecisions() {
  let now=Date(timeIntervalSince1970:1_783_074_300)
  let p=Pack("p","1",[Requirement("r",minIndependentSources:2)])
  let a=Witness("a","r","A","doc:a","SUPPORTS",now.addingTimeInterval(-300))
  let b=Witness("b","r","B","doc:b","SUPPORTS",now.addingTimeInterval(-300))
  XCTAssertEqual(Gate.evaluate(p,[a,b],asOf:now).verdict,"ADMIT")
  XCTAssertEqual(Gate.evaluate(p,[a,Witness("b","r","A","doc:b","SUPPORTS",now.addingTimeInterval(-300))],asOf:now).verdict,"INCONCLUSIVE")
  XCTAssertEqual(Gate.evaluate(p,[a,Witness("b","r","B","doc:b","CONTRADICTS",now.addingTimeInterval(-300))],asOf:now).verdict,"REFUSE")
 }
}
