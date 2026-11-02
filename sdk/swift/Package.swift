// swift-tools-version: 5.9
import PackageDescription
let package = Package(
 name: "QualityRag",
 platforms: [.macOS(.v13),.iOS(.v16)],
 products: [.library(name: "QualityRag", targets: ["QualityRag"])],
 targets: [.target(name: "QualityRag"),.testTarget(name: "QualityRagTests", dependencies: ["QualityRag"])]
)
