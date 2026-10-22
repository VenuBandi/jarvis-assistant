// swift-tools-version:5.10
// Jarvis Bar: the menu-bar app for Jarvis (J1b). No third-party packages.
import PackageDescription

let package = Package(
    name: "JarvisBar",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "JarvisBarCore"),
        .executableTarget(name: "JarvisBar", dependencies: ["JarvisBarCore"]),
        .testTarget(name: "JarvisBarCoreTests", dependencies: ["JarvisBarCore"]),
    ]
)
