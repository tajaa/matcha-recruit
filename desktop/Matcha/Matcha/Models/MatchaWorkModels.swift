import Foundation

struct MWThread: Codable, Identifiable {
    let id: String
    var title: String
    let taskType: String
    var status: String
    var version: Int
    var isPinned: Bool
    let createdAt: String
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version
        case taskType = "task_type"
        case isPinned = "is_pinned"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct MWCreateThreadResponse: Codable {
    let id: String
    let title: String
    let taskType: String
    let status: String
    let version: Int
    let isPinned: Bool
    let createdAt: String
    let assistantReply: String?
    let pdfUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version
        case taskType = "task_type"
        case isPinned = "is_pinned"
        case createdAt = "created_at"
        case assistantReply = "assistant_reply"
        case pdfUrl = "pdf_url"
    }

    func toThread() -> MWThread {
        MWThread(id: id, title: title, taskType: taskType, status: status,
                 version: version, isPinned: isPinned, createdAt: createdAt, updatedAt: nil)
    }
}

struct MWMessage: Codable, Identifiable {
    let id: String
    let threadId: String
    let role: String
    let content: String
    let versionCreated: Int?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case threadId = "thread_id"
        case versionCreated = "version_created"
        case createdAt = "created_at"
    }
}

// Flat response matching backend ThreadDetailResponse
struct MWThreadDetail: Codable {
    let id: String
    let title: String
    let taskType: String
    let status: String
    let version: Int
    let isPinned: Bool
    let createdAt: String
    let updatedAt: String
    let messages: [MWMessage]
    let currentState: [String: AnyCodable]

    var thread: MWThread {
        MWThread(id: id, title: title, taskType: taskType, status: status,
                 version: version, isPinned: isPinned, createdAt: createdAt, updatedAt: updatedAt)
    }

    enum CodingKeys: String, CodingKey {
        case id, title, status, version, messages
        case taskType = "task_type"
        case isPinned = "is_pinned"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case currentState = "current_state"
    }
}

struct MWSendMessageResponse: Codable {
    let userMessage: MWMessage
    let assistantMessage: MWMessage?
    let currentState: [String: AnyCodable]?
    let version: Int?
    let pdfUrl: String?
    let tokenUsage: MWTokenUsage?

    enum CodingKeys: String, CodingKey {
        case version
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
        case currentState = "current_state"
        case pdfUrl = "pdf_url"
        case tokenUsage = "token_usage"
    }
}

struct MWTokenUsage: Codable {
    let inputTokens: Int?
    let outputTokens: Int?
    enum CodingKeys: String, CodingKey {
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
    }
}

struct MWDocumentVersion: Codable, Identifiable {
    var id: Int { version }
    let version: Int
    let diffSummary: String?
    let createdAt: String
    enum CodingKeys: String, CodingKey {
        case version
        case diffSummary = "diff_summary"
        case createdAt = "created_at"
    }
}

struct MWCreateThreadRequest: Codable {
    let title: String?
    let taskType: String
    let initialMessage: String?
    enum CodingKeys: String, CodingKey {
        case title
        case taskType = "task_type"
        case initialMessage = "initial_message"
    }
}


struct MWPinRequest: Codable {
    let pinned: Bool
}

struct MWRevertRequest: Codable {
    let version: Int
}

// AnyCodable for flexible JSON
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Bool.self) { value = v }
        else if let v = try? container.decode(Int.self) { value = v }
        else if let v = try? container.decode(Double.self) { value = v }
        else if let v = try? container.decode(String.self) { value = v }
        else if let v = try? container.decode([String: AnyCodable].self) { value = v }
        else if let v = try? container.decode([AnyCodable].self) { value = v }
        else { value = NSNull() }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let v as Bool: try container.encode(v)
        case let v as Int: try container.encode(v)
        case let v as Double: try container.encode(v)
        case let v as String: try container.encode(v)
        case let v as [String: AnyCodable]: try container.encode(v)
        case let v as [AnyCodable]: try container.encode(v)
        default: try container.encodeNil()
        }
    }
}
