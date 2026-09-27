import Foundation

/// The app-server 0.155.1 wire format uses camelCase (unlike Matcha's API).
/// Unknown fields/events remain readable without turning them into capabilities.
enum CodexJSON: Codable, Sendable, Equatable {
    case object([String: CodexJSON]), array([CodexJSON]), string(String), number(Double), bool(Bool), null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode([CodexJSON].self) { self = .array(v) }
        else { self = .object(try c.decode([String: CodexJSON].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }

    subscript(_ key: String) -> CodexJSON {
        if case .object(let v) = self { return v[key] ?? .null }
        return .null
    }
    var string: String? { if case .string(let v) = self { return v }; return nil }
    var array: [CodexJSON] { if case .array(let v) = self { return v }; return [] }
    var isTrue: Bool { self == .bool(true) }
}

struct CodexFailure: LocalizedError, Sendable {
    let message: String
    var errorDescription: String? { message }
}

struct CodexLineFramer {
    static let maximumBytes = 4 * 1024 * 1024
    private var buffer = Data()

    mutating func append(_ data: Data) throws -> [CodexJSON] {
        buffer.append(data)
        var messages: [CodexJSON] = []
        while let end = buffer.firstIndex(of: 10) {
            let line = buffer[..<end]
            guard line.count <= Self.maximumBytes else { throw CodexFailure(message: "Codex sent an oversized message.") }
            if !line.isEmpty { messages.append(try JSONDecoder().decode(CodexJSON.self, from: line)) }
            buffer.removeSubrange(...end)
        }
        guard buffer.count <= Self.maximumBytes else { throw CodexFailure(message: "Codex sent an oversized message.") }
        return messages
    }
}

/// Batches `item/agentMessage/delta` text so the UI sees one event per flush
/// interval instead of one per few characters. A thread switch flushes first,
/// so text is never attributed to the wrong thread.
struct CodexDeltaCoalescer {
    static let method = "item/agentMessage/delta"
    private var text = ""
    private var thread: CodexJSON = .null

    /// The pending batch for the previous thread, when `params` starts another.
    mutating func append(_ params: CodexJSON) -> CodexJSON? {
        guard let delta = params["delta"].string else { return nil }
        let flushed = params["threadId"] != thread ? take() : nil
        thread = params["threadId"]
        text += delta
        return flushed
    }

    mutating func take() -> CodexJSON? {
        guard !text.isEmpty else { return nil }
        defer { text = "" }
        return .object(["method": .string(Self.method), "params": .object(["threadId": thread, "delta": .string(text)])])
    }
}

/// A completed turn alone is not publication evidence. MCP may have failed.
enum CodexPublication {
    static func filename(item: CodexJSON, taskID: String) -> String? {
        guard item["type"].string == "mcpToolCall", item["server"].string == "matcha",
              item["tool"].string == "attach_research_report", item["status"].string == "completed",
              item["error"] == .null else { return nil }
        var payloads = [item["result"]["structuredContent"]]
        for content in item["result"]["content"].array {
            if content["type"].string == "text", let text = content["text"].string,
               let data = text.data(using: .utf8), let value = try? JSONDecoder().decode(CodexJSON.self, from: data) {
                payloads.append(value)
            }
        }
        return payloads.first { $0["task_id"].string?.lowercased() == taskID.lowercased()
            && $0["attached"].isTrue && $0["column"].string == "review" }?["filename"].string
    }
}

struct MWLocalCodexToken: Decodable {
    let access_token: String
    let expires_at: String
    let resource: String
    let grant_id: String
}

struct MWLocalCodexRelease: Decodable {
    let released: Bool
    let column: String?
}
