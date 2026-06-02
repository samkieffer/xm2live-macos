// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "XM2Live",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "XM2Live",
            path: "Sources/XM2Live"
        )
    ]
)
