import XCTest
import Foundation
@testable import QualityRag
final class ConformanceTests: XCTestCase {
 func testSharedFixtures() throws {
  let location = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("../../conformance/v0.1.json")
  let data = try Data(contentsOf: location)
  let suite = try XCTUnwrap(JSONSerialization.jsonObject(with:data) as? [String:Any])
  let parser=ISO8601DateFormatter()
  let now=try XCTUnwrap(parser.date(from:suite["as_of"] as! String))
  let pack=Pack("conformance","1",[Requirement("r",minIndependentSources:2,maxAgeSeconds:3600)])
  for item in suite["cases"] as! [[String:Any]] {
   let name=item["name"] as! String
   let witnesses=(item["evidence"] as! [[String]]).map { row in
    Witness(row[0],"r",row[1],"doc:"+row[0],row[2],parser.date(from:row.count>3 ? row[3] : "2026-11-02T10:00:00Z")!)
   }
   let result=Gate.evaluate(pack,witnesses,asOf:now)
   XCTAssertEqual(result.verdict,item["verdict"] as? String,name)
   XCTAssertEqual(result.findings[0].reasons,item["reasons"] as? [String],name)
  }
 }
}
