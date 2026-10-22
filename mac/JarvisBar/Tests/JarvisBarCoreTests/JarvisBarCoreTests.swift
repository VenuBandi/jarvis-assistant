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

    func testURLKeepsQuery() {
        let c = JarvisClient(base: URL(string: "http://127.0.0.1:8770/")!, token: "x")
        XCTAssertEqual(c.url("api/conversation", query: [URLQueryItem(name: "conv", value: "default")]).absoluteString,
                       "http://127.0.0.1:8770/api/conversation?conv=default")
        XCTAssertEqual(c.url("api/state").absoluteString, "http://127.0.0.1:8770/api/state")
    }

    func testMissingToken() {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        XCTAssertThrowsError(try JarvisClient.loadToken(root: root))
    }
}

final class VoiceLogicTests: XCTestCase {
    func feed(_ d: inout SpeechEndDetector, _ level: Float, _ seconds: Double) -> SpeechEndDetector.Result {
        var r = SpeechEndDetector.Result.keepListening
        for _ in 0..<Int(seconds * 10) { r = d.feed(rms: level, seconds: 0.1); if r != .keepListening { break } }
        return r
    }

    func testEndsAfterSilenceFollowingSpeech() {
        var d = SpeechEndDetector()
        XCTAssertEqual(feed(&d, 0.002, 0.3), .keepListening)   // room noise
        XCTAssertEqual(feed(&d, 0.2, 1.5), .keepListening)     // speaking
        XCTAssertEqual(feed(&d, 0.003, 0.5), .keepListening)   // short pause between words
        XCTAssertEqual(feed(&d, 0.2, 0.5), .keepListening)
        XCTAssertEqual(feed(&d, 0.003, 1.2), .speechEnded)
    }

    func testNoSpeech() {
        var d = SpeechEndDetector()
        XCTAssertEqual(feed(&d, 0.002, 7), .noSpeech)
    }

    func testNoisyRoomRaisesThreshold() {
        var d = SpeechEndDetector()
        _ = feed(&d, 0.05, 0.3)                                // loud room
        XCTAssertEqual(d.threshold, 0.15, accuracy: 0.001)
        XCTAssertEqual(feed(&d, 0.06, 7), .noSpeech)           // room noise is not speech
        XCTAssertFalse(d.heardSpeech)
    }

    func testSpeakingRightAfterTheChime() {
        var d = SpeechEndDetector()
        XCTAssertEqual(feed(&d, 0.2, 0.4), .keepListening)     // talks at once: no quiet room sample yet
        XCTAssertEqual(feed(&d, 0.004, 0.2), .keepListening)   // gap between words
        XCTAssertEqual(feed(&d, 0.2, 1.0), .keepListening)
        XCTAssertTrue(d.heardSpeech)
        XCTAssertEqual(feed(&d, 0.004, 1.2), .speechEnded)
    }

    func testMaxLength() {
        var d = SpeechEndDetector()
        var r = SpeechEndDetector.Result.keepListening
        for i in 0..<320 where r == .keepListening { r = d.feed(rms: i % 5 == 0 ? 0.004 : 0.2, seconds: 0.1) }
        XCTAssertEqual(r, .tooLong)                            // talks non-stop for 30 s
    }

    func testWav() {
        let w = wavData([0, 1, -1], sampleRate: 16000)
        XCTAssertEqual(w.count, 44 + 6)
        XCTAssertEqual(String(data: w.prefix(4), encoding: .ascii), "RIFF")
        XCTAssertEqual(String(data: w.subdata(in: 8..<12), encoding: .ascii), "WAVE")
        XCTAssertEqual(w.subdata(in: 44..<50), Data([0, 0, 0xFF, 0x7F, 0x01, 0x80]))
    }

    func testRms() {
        XCTAssertEqual(rms([0.5, -0.5]), 0.5, accuracy: 0.0001)
        XCTAssertEqual(rms([]), 0)
    }

    func testSpokenText() {
        XCTAssertEqual(spokenText("The **agent** is `working`. See [the report](https://x.y/z) or https://a.b/c"),
                       "The agent is working. See the report or link")
        XCTAssertEqual(spokenText("# Status\n- step 6"), "Status - step 6")
    }

    func testCleanTranscript() {
        XCTAssertEqual(cleanTranscript(" Jarvis, what is the status?\n"), "Jarvis, what is the status?")
        XCTAssertEqual(cleanTranscript("[BLANK_AUDIO]"), "")
        XCTAssertEqual(cleanTranscript(" (music) hello [noise] there"), "hello there")
    }
}

final class SentenceSplitterTests: XCTestCase {
    func testSentencesAsTheyArrive() {
        var s = SentenceSplitter()
        XCTAssertEqual(s.feed("The project is on "), [])
        XCTAssertEqual(s.feed("step 6. One decision"), ["The project is on step 6."])
        XCTAssertEqual(s.feed(" is waiting for you."), [])        // no space after the last dot yet
        XCTAssertEqual(s.flush(), "One decision is waiting for you.")
        XCTAssertNil(s.flush())
    }

    func testNumbersAndVersionsAreNotCut() {
        var s = SentenceSplitter()
        XCTAssertEqual(s.feed("Lag goes to 3.5 hours in v1.2 of the model. Next"), ["Lag goes to 3.5 hours in v1.2 of the model."])
    }

    func testShortPiecesWaitForMore() {
        var s = SentenceSplitter()
        XCTAssertEqual(s.feed("Yes. "), [])
        XCTAssertEqual(s.feed("It is done now. "), ["Yes. It is done now."])
    }

    func testLineBreaksAndQuestions() {
        var s = SentenceSplitter()
        XCTAssertEqual(s.feed("Shall I read the decision? "), ["Shall I read the decision?"])
        XCTAssertEqual(s.feed("First item here\nSecond"), ["First item here"])
        XCTAssertEqual(s.flush(), "Second")
    }
}

/// Fake network for JarvisClient: answers every request with `FakeJarvis.reply` and records the request.
final class FakeJarvis: URLProtocol {
    static var status = 200
    static var reply = Data()
    static var lastRequest: URLRequest?
    static var lastBody: [String: Any]?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        FakeJarvis.lastRequest = request
        if let s = request.httpBodyStream {
            s.open(); var d = Data(); var buf = [UInt8](repeating: 0, count: 4096)
            while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; d.append(buf, count: n) }
            s.close()
            FakeJarvis.lastBody = try? JSONSerialization.jsonObject(with: d) as? [String: Any]
        }
        let resp = HTTPURLResponse(url: request.url!, statusCode: FakeJarvis.status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: FakeJarvis.reply)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class StreamClientTests: XCTestCase {
    func client() -> JarvisClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [FakeJarvis.self]
        return JarvisClient(base: URL(string: "http://127.0.0.1:8770/")!, token: "fake-token", configuration: cfg)
    }

    func testStreamItemsInOrder() async throws {
        FakeJarvis.status = 200
        FakeJarvis.reply = Data("""
        {"type": "text", "delta": "Step 6 is signed off. "}
        {"type": "text", "delta": "One decision waits."}
        {"type": "done", "reply": "Step 6 is signed off. One decision waits.", "model": "m", "steps": [], "pending": null, "error": ""}

        """.utf8)
        var deltas: [String] = []
        var done: StreamItem?
        for try await item in try await client().chatStream("status?", voice: true) {
            if item.type == "text" { deltas.append(item.delta ?? "") } else { done = item }
        }
        XCTAssertEqual(deltas, ["Step 6 is signed off. ", "One decision waits."])
        XCTAssertEqual(done?.reply, "Step 6 is signed off. One decision waits.")
        XCTAssertEqual(FakeJarvis.lastRequest?.url?.path, "/api/chat/stream")
        XCTAssertEqual(FakeJarvis.lastRequest?.value(forHTTPHeaderField: "X-Jarvis-Token"), "fake-token")
        XCTAssertEqual(FakeJarvis.lastBody?["voice"] as? Bool, true)
    }

    func testOldJarvisWithoutStreamGives404() async {
        FakeJarvis.status = 404
        FakeJarvis.reply = Data(#"{"detail":"Not Found"}"#.utf8)
        do {
            _ = try await client().chatStream("hi")
            XCTFail("expected 404")
        } catch JarvisError.http(let code) {
            XCTAssertEqual(code, 404)
        } catch { XCTFail("\(error)") }
    }
}
