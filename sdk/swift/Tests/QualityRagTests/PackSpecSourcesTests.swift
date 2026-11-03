import XCTest
@testable import QualityRag

final class PackSpecSourcesTests:XCTestCase {
 func testInlineAndFileFailClosed() async throws {
   let load=try PackSpecSources.property("""
     {"id":"eu","version":"1","requirements":[{"id":"general"},{"id":"control"}]}
     """)
   let result=try await load()
   XCTAssertEqual(result.id,"eu")
   let path=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
   try "{}".write(to:path,atomically:true,encoding:.utf8)
   defer {try? FileManager.default.removeItem(at:path)}
   let broken=PackSpecSources.file(path)
   do {_ = try await broken(); XCTFail("Invalid policy accepted")} catch {}
 }
 func testStudioRequiresHttps() {
   XCTAssertThrowsError(try PackSpecSources.studio(base:URL(string:"http://example.com")!,
      token:"secret",service:"app",environment:"dev"))
 }
}
