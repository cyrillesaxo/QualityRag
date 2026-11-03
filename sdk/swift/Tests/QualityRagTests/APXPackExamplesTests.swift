import Foundation
import XCTest
@testable import QualityRag

final class APXPackExamplesTests: XCTestCase {
 func testAllTwelveCases() throws {
  let path=URL(fileURLWithPath:FileManager.default.currentDirectoryPath)
    .appendingPathComponent("../../examples/apx-packspecs/fixtures.json")
  let data=try Data(contentsOf:path)
  let root=try XCTUnwrap(JSONSerialization.jsonObject(with:data) as? [String:Any])
  let clock=ISO8601DateFormatter()
  let at=try XCTUnwrap(clock.date(from:root["as_of"] as! String))
  var count=0
  for domain in root["scenarios"] as! [[String:Any]] {
   let raw=domain["pack"] as! [String:Any]
   let requirements=(raw["requirements"] as! [[String:Any]]).map {
    Requirement($0["id"] as! String)
   }
   let pack=Pack(raw["id"] as! String,raw["version"] as! String,requirements)
   for example in domain["cases"] as! [[String:Any]] {
    let witnesses=try (example["evidence"] as! [[String:Any]]).map { w throws -> Witness in
     let observed=try XCTUnwrap(clock.date(from:w["observed_at"] as! String))
     return Witness(w["id"] as! String,w["requirement_id"] as! String,
       w["origin"] as! String,w["source_ref"] as! String,w["status"] as! String,observed)
    }
    XCTAssertEqual(Gate.evaluate(pack,witnesses,asOf:at).verdict,example["expected"] as? String)
    count+=1
   }
  }
  XCTAssertEqual(12,count)
 }
}
