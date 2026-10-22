// Client for the local Jarvis server (127.0.0.1:8770): the same token-protected endpoints the web page uses.
// The token is read from <JarvisRoot>/data/jarvis_app/api_token (mode 600) and never logged or shown.
import Foundation

public enum JSONValue: Decodable, Equatable, CustomStringConvertible {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    public var description: String {
        switch self {
        case .string(let s): return s
        case .number(let n): return n == n.rounded() ? String(Int(n)) : String(n)
        case .bool(let b): return String(b)
        case .array(let a): return "[" + a.map(\.description).joined(separator: ", ") + "]"
        case .object(let o): return o.keys.sorted().map { "\($0): \(o[$0]!)" }.joined(separator: ", ")
        case .null: return "null"
        }
    }
}

public struct JarvisState: Decodable {
    public struct Active: Decodable { public let key: String; public let label: String }
    public let agent_state: String
    public let active: Active
    public let pending: [Pending]
}

public struct Pending: Decodable, Identifiable, Equatable {
    public let id: String
    public let tool: String
    public let args: [String: JSONValue]
}

public struct Message: Decodable, Equatable {
    public let role: String
    public let content: String
    public let at: String
}

public struct ChatReply: Decodable {
    public let reply: String?
    public let error: String?
}

public enum JarvisError: Error, CustomStringConvertible {
    case token(String), http(Int)
    public var description: String {
        switch self {
        case .token(let s): return s
        case .http(let c): return "Jarvis answered HTTP \(c)"
        }
    }
}

public final class JarvisClient {
    public let base: URL
    private let token: String
    private let session: URLSession

    public init(base: URL, token: String) {
        self.base = base
        self.token = token
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 300  // a chat turn can take minutes with a slow brain
        session = URLSession(configuration: cfg)
    }

    /// Reads the per-install API token; refuses a file that is not mode 600.
    public static func loadToken(root: URL) throws -> String {
        let path = root.appendingPathComponent("data/jarvis_app/api_token").path
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: path),
              let mode = attrs[.posixPermissions] as? NSNumber else { throw JarvisError.token("Jarvis token not found") }
        guard mode.intValue & 0o777 == 0o600 else { throw JarvisError.token("Jarvis token must be mode 600") }
        let t = (try? String(contentsOfFile: path, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !t.isEmpty else { throw JarvisError.token("Jarvis token is empty") }
        return t
    }

    func url(_ path: String, query: [URLQueryItem] = []) -> URL {
        var c = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { c.queryItems = query }
        return c.url!
    }

    private func call(_ path: String, query: [URLQueryItem] = [], body: [String: Any]? = nil) async throws -> Data {
        var req = URLRequest(url: url(path, query: query))
        req.setValue(token, forHTTPHeaderField: "X-Jarvis-Token")
        if let body {
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, resp) = try await session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else { throw JarvisError.http(code) }
        return data
    }

    public func state() async throws -> JarvisState {
        try JSONDecoder().decode(JarvisState.self, from: try await call("api/state"))
    }

    public func conversation(_ conv: String = "default") async throws -> [Message] {
        let q = [URLQueryItem(name: "conv", value: conv)]
        return try JSONDecoder().decode([Message].self, from: try await call("api/conversation", query: q))
    }

    /// `voice`: the request was spoken, so Jarvis keeps the reply short for reading aloud.
    public func chat(_ text: String, conv: String = "default", voice: Bool = false) async throws -> ChatReply {
        try JSONDecoder().decode(ChatReply.self, from: try await call("api/chat",
                                                                      body: ["conv": conv, "text": text, "voice": voice]))
    }

    public func confirm(_ id: String, approve: Bool) async throws -> ChatReply {
        try JSONDecoder().decode(ChatReply.self, from: try await call("api/confirm", body: ["id": id, "approve": approve]))
    }

    public func stop() async throws {
        _ = try await call("api/stop", body: [:])
    }
}
