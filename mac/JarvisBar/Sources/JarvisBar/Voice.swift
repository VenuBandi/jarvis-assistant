// J1c voice: microphone recording (push-to-talk), local speech-to-text with whisper.cpp, spoken replies.
// Audio stays in memory; the one temporary WAV file whisper needs is deleted right after transcription.
// Nothing audio-related is logged or sent anywhere; only the recognised text goes to Jarvis.
import AVFoundation
import Foundation
import JarvisBarCore

final class Recorder {
    private let engine = AVAudioEngine()
    private let lock = NSLock()
    private var samples: [Float] = []
    private var detector = SpeechEndDetector()
    private var done = false
    var onEnd: ((SpeechEndDetector.Result, [Float]) -> Void)?
    var onLevel: ((Float) -> Void)?  // loudness of each ~0.1 s chunk, for the circle's bars

    static func requestPermission(_ then: @escaping (Bool) -> Void) {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: then(true)
        case .notDetermined: AVCaptureDevice.requestAccess(for: .audio) { ok in DispatchQueue.main.async { then(ok) } }
        default: then(false)
        }
    }

    func start() throws {
        lock.lock(); samples = []; detector = SpeechEndDetector(); done = false; lock.unlock()
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard let outFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16000, channels: 1, interleaved: false),
              let converter = AVAudioConverter(from: inFormat, to: outFormat) else {
            throw NSError(domain: "JarvisBar", code: 1, userInfo: [NSLocalizedDescriptionKey: "microphone format not supported"])
        }
        // ~0.1 s chunks at the input rate
        input.installTap(onBus: 0, bufferSize: AVAudioFrameCount(inFormat.sampleRate / 10), format: inFormat) { [weak self] buf, _ in
            let cap = AVAudioFrameCount(Double(buf.frameLength) * 16000 / inFormat.sampleRate) + 64
            guard let self, let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: cap) else { return }
            var fed = false
            var err: NSError?
            converter.convert(to: out, error: &err) { _, status in
                if fed { status.pointee = .noDataNow; return nil }
                fed = true
                status.pointee = .haveData
                return buf
            }
            guard err == nil, let ch = out.floatChannelData else { return }
            self.handle(Array(UnsafeBufferPointer(start: ch[0], count: Int(out.frameLength))))
        }
        engine.prepare()
        try engine.start()
    }

    private func handle(_ chunk: [Float]) {
        lock.lock()
        if done { lock.unlock(); return }
        samples.append(contentsOf: chunk)
        let level = rms(chunk)
        let r = detector.feed(rms: level, seconds: Double(chunk.count) / 16000)
        DispatchQueue.main.async { self.onLevel?(level) }
        if r != .keepListening { done = true }
        let captured = done ? samples : []
        lock.unlock()
        if r != .keepListening { DispatchQueue.main.async { self.finish(r, captured) } }
    }

    /// Ends the recording now (Stop, or the Done button). Speech so far is kept.
    func stopNow() {
        lock.lock()
        let already = done
        done = true
        let captured = samples
        let heard = detector.heardSpeech
        lock.unlock()
        if !already { finish(heard ? .speechEnded : .noSpeech, captured) }
    }

    func cancel() {
        lock.lock(); done = true; samples = []; lock.unlock()
        teardown()
    }

    private func finish(_ r: SpeechEndDetector.Result, _ captured: [Float]) {
        teardown()
        onEnd?(r, captured)
    }

    private func teardown() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }
}

struct Transcriber {
    static let cli = "/opt/homebrew/bin/whisper-cli"
    let model: URL

    var available: Bool {
        FileManager.default.isExecutableFile(atPath: Self.cli) && FileManager.default.fileExists(atPath: model.path)
    }

    /// Runs whisper.cpp on the samples (16 kHz mono). Blocking: call off the main thread.
    func transcribe(_ samples: [Float]) throws -> String {
        let wav = FileManager.default.temporaryDirectory.appendingPathComponent("jarvis-\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: wav) }
        try wavData(samples).write(to: wav, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: wav.path)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: Self.cli)
        p.arguments = ["-m", model.path, "-f", wav.path, "-l", "en", "-nt", "-np",
                       "--prompt", "Jarvis, FlightOps."]
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        try p.run()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        guard p.terminationStatus == 0 else {
            throw NSError(domain: "JarvisBar", code: 2, userInfo: [NSLocalizedDescriptionKey: "speech-to-text failed"])
        }
        return cleanTranscript(String(decoding: data, as: UTF8.self))
    }
}

final class Speaker: NSObject, AVSpeechSynthesizerDelegate, @unchecked Sendable {  // used from the main thread only
    private let synth = AVSpeechSynthesizer()
    private var queued = 0  // sentences waiting or being spoken; onFinish fires when the last one is done
    var onFinish: (() -> Void)?
    var voiceID: String?

    override init() {
        super.init()
        synth.delegate = self
    }

    var speaking: Bool { synth.isSpeaking }

    func say(_ text: String) {
        let t = spokenText(text)
        guard !t.isEmpty else { if queued == 0 { onFinish?() }; return }
        let u = AVSpeechUtterance(string: t)
        if let voiceID, let v = AVSpeechSynthesisVoice(identifier: voiceID) { u.voice = v }
        queued += 1
        synth.speak(u)
    }

    func stop() {
        queued = 0
        synth.stopSpeaking(at: .immediate)
        onFinish?()
    }

    private func spoke() {
        DispatchQueue.main.async {
            guard self.queued > 0 else { return }
            self.queued -= 1
            if self.queued == 0 { self.onFinish?() }
        }
    }

    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { spoke() }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { spoke() }
}
