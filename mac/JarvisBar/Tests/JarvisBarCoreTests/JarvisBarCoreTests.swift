import Foundation
import XCTest
@testable import JarvisBarCore

final class HoldDetectorTests: XCTestCase {
    func testFiresOnceAfterHold() {
        var h = HoldDetector(hold: 3)
        XCTAssertTrue(h.press(at: 10))
        XCTAssertFalse(h.check(at: 12))
        XCTAssertTrue(h.check(at: 13))
        XCTAssertFalse(h.check(at: 14))          // only once
        XCTAssertFalse(h.release(at: 15))        // released after firing: not a cancel
    }

    func testEarlyReleaseCancels() {
        var h = HoldDetector(hold: 3)
        XCTAssertTrue(h.press(at: 0))
        XCTAssertTrue(h.release(at: 1.5))
        XCTAssertFalse(h.check(at: 3))           // the scheduled check after a release does nothing
    }

    func testKeyRepeatIgnoredWhileHeld() {
        var h = HoldDetector(hold: 3)
        XCTAssertTrue(h.press(at: 0))
        XCTAssertFalse(h.press(at: 0.5))
        XCTAssertFalse(h.press(at: 2.9))
        XCTAssertTrue(h.check(at: 3))            // timing counts from the first press
    }

    func testNewHoldAfterRelease() {
        var h = HoldDetector(hold: 3)
        _ = h.press(at: 0)
        h.release(at: 1)
        XCTAssertTrue(h.press(at: 2))
        XCTAssertFalse(h.check(at: 3))           // old press must not count
        XCTAssertTrue(h.check(at: 5))
    }

    func testReleaseWithoutPress() {
        var h = HoldDetector(hold: 3)
        XCTAssertFalse(h.release(at: 1))
    }
}

final class OptionSideTests: XCTestCase {
    func testSides() {
        let option: UInt64 = 0x80000                 // device-independent Option bit, set for either side
        XCTAssertEqual(optionSide(flags: option | 0x20), .left)
        XCTAssertEqual(optionSide(flags: option | 0x40), .right)
        XCTAssertEqual(optionSide(flags: option | 0x60), .both)
        XCTAssertEqual(optionSide(flags: 0), .none)
        XCTAssertEqual(optionSide(flags: 0x100), .none)   // other bits only
    }
}

final class APITests: XCTestCase {
    func testDecodeState() throws {
        let json = """
        {"agent_state":"idle","active":{"key":"local-qwen","label":"Qwen3 8B","provider":"ollama","model":"q"},
         "models":[],"tools":[],"pending":[{"id":"0123456789ab","conv_id":"default","tool":"remember",
         "args":{"text":"likes tea","n":2,"ok":true},"call_id":null,"status":"pending","created_at":"t","decided_at":null}]}
        """
        let s = try JSONDecoder().decode(JarvisState.self, from: Data(json.utf8))
        XCTAssertEqual(s.agent_state, "idle")
        XCTAssertEqual(s.active.label, "Qwen3 8B")
        XCTAssertEqual(s.pending.first?.tool, "remember")
        XCTAssertEqual(JSONValue.object(s.pending[0].args).description, "n: 2, ok: true, text: likes tea")
    }

    func testTokenMustBeMode600() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let dir = root.appendingPathComponent("data/jarvis_app")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("api_token")
        try "fake-token\n".write(to: file, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o644], ofItemAtPath: file.path)
        XCTAssertThrowsError(try JarvisClient.loadToken(root: root))
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        XCTAssertEqual(try JarvisClient.loadToken(root: root), "fake-token")
    }

    func testMissingToken() {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        XCTAssertThrowsError(try JarvisClient.loadToken(root: root))
    }
}
