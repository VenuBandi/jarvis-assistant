// Voice logic without AVFoundation, so it can be unit-tested: end-of-speech detection, WAV encoding, spoken text.
import Foundation

/// Decides when a push-to-talk recording ends, from the loudness (RMS) of short audio chunks (~0.1 s).
/// Room noise = the quietest chunk so far (gaps between words count too, so speaking right after the chime works);
/// speech = louder than max(minLevel, 3 × room noise). Ends after `silenceToEnd` seconds of quiet following speech,
/// gives up if nobody speaks within `noSpeechTimeout`, and stops at `maxLength` in any case.
public struct SpeechEndDetector {
    public enum Result: Equatable { case keepListening, speechEnded, noSpeech, tooLong }

    public var silenceToEnd = 1.0, noSpeechTimeout = 6.0, maxLength = 30.0, minLevel: Float = 0.015
    public private(set) var elapsed = 0.0
    public private(set) var heardSpeech = false
    private var noise = Float.greatestFiniteMagnitude
    private var quietFor = 0.0

    public init() {}

    public var threshold: Float { noise == .greatestFiniteMagnitude ? minLevel : max(minLevel, noise * 3) }

    public mutating func feed(rms: Float, seconds: Double) -> Result {
        elapsed += seconds
        noise = min(noise, rms)
        if rms > threshold {
            heardSpeech = true
            quietFor = 0
        } else if heardSpeech {
            quietFor += seconds
        }
        if heardSpeech && quietFor >= silenceToEnd { return .speechEnded }
        if !heardSpeech && elapsed >= noSpeechTimeout { return .noSpeech }
        if elapsed >= maxLength { return heardSpeech ? .tooLong : .noSpeech }
        return .keepListening
    }
}

public func rms(_ samples: [Float]) -> Float {
    guard !samples.isEmpty else { return 0 }
    return (samples.reduce(0) { $0 + $1 * $1 } / Float(samples.count)).squareRoot()
}

/// 16-bit PCM mono WAV, the format whisper.cpp reads.
public func wavData(_ samples: [Float], sampleRate: Int = 16000) -> Data {
    var d = Data()
    func u32(_ v: UInt32) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
    func u16(_ v: UInt16) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
    let bytes = UInt32(samples.count * 2)
    d.append(contentsOf: Array("RIFF".utf8)); u32(36 + bytes); d.append(contentsOf: Array("WAVE".utf8))
    d.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1)
    u32(UInt32(sampleRate)); u32(UInt32(sampleRate * 2)); u16(2); u16(16)
    d.append(contentsOf: Array("data".utf8)); u32(bytes)
    for s in samples {
        let v = Int16(max(-1, min(1, s)) * Float(Int16.max))
        u16(UInt16(bitPattern: v))
    }
    return d
}

/// Text as it should be spoken: no Markdown symbols, links read as "link".
public func spokenText(_ text: String) -> String {
    var t = text.replacingOccurrences(of: #"\[([^\]]+)\]\([^)]+\)"#, with: "$1", options: .regularExpression)
    t = t.replacingOccurrences(of: #"https?://\S+"#, with: "link", options: .regularExpression)
    t = t.replacingOccurrences(of: #"[*_`#>|]+"#, with: "", options: .regularExpression)
    t = t.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
    return t.trimmingCharacters(in: .whitespacesAndNewlines)
}

/// whisper.cpp output → the request text (drops blank-audio markers like "[BLANK_AUDIO]" and "(music)").
public func cleanTranscript(_ raw: String) -> String {
    let t = raw.replacingOccurrences(of: #"\[[^\]]*\]|\([^)]*\)"#, with: "", options: .regularExpression)
    return t.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

/// Cuts a streamed answer into sentences so each one can be spoken as soon as it is complete.
/// A sentence ends at . ! ? or a line break followed by whitespace (so "3.5" or "v1.2" are not cut); pieces
/// shorter than `minLength` wait for the next sentence, so speech does not stutter on fragments like "Yes.".
public struct SentenceSplitter {
    public var minLength = 12
    private var buffer = ""

    public init() {}

    public mutating func feed(_ piece: String) -> [String] {
        buffer += piece
        var out: [String] = []
        var start = buffer.startIndex
        var i = buffer.startIndex
        while i < buffer.endIndex {
            let c = buffer[i]
            let next = buffer.index(after: i)
            let ends = c == "\n" || ("!?.".contains(c) && next < buffer.endIndex && buffer[next].isWhitespace)
            if ends {
                let s = buffer[start..<next].trimmingCharacters(in: .whitespacesAndNewlines)
                if s.count >= minLength {
                    out.append(s)
                    start = next
                }
            }
            i = next
        }
        buffer = String(buffer[start...])
        return out
    }

    /// Whatever is left when the answer is complete.
    public mutating func flush() -> String? {
        let s = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
        buffer = ""
        return s.isEmpty ? nil : s
    }
}
