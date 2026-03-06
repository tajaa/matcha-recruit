import Foundation

private let mwISO8601WithFractionalSeconds: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
}()

private let mwISO8601DateFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter
}()

func parseMWDate(_ iso: String) -> Date? {
    mwISO8601WithFractionalSeconds.date(from: iso) ?? mwISO8601DateFormatter.date(from: iso)
}

enum MWTaskType: String, Codable {
    case offerLetter = "offer_letter"
    case review
    case workbook
    case onboarding
    case presentation
    case handbook
    case chat

    var label: String {
        switch self {
        case .chat:
            return "chat"
        case .review:
            return "anonymized review"
        case .workbook:
            return "HR workbook"
        case .onboarding:
            return "employee onboarding"
        case .presentation:
            return "presentation"
        case .handbook:
            return "employee handbook"
        case .offerLetter:
            return "offer letter"
        }
    }
}

func inferMWTaskType(from state: [String: AnyCodable]) -> MWTaskType {
    if state["candidate_name"] != nil || state["position_title"] != nil || state["salary"] != nil {
        return .offerLetter
    }
    if state["overall_rating"] != nil || state["review_title"] != nil || state["review_request_statuses"] != nil {
        return .review
    }
    if state.keys.contains(where: { $0.hasPrefix("handbook_") }) {
        return .handbook
    }
    if state["sections"] != nil || state["workbook_title"] != nil {
        return .workbook
    }
    if state["presentation_title"] != nil || state["slides"] != nil {
        return .presentation
    }
    if state["employees"] != nil || state["batch_status"] != nil {
        return .onboarding
    }
    return .chat
}

struct MWThread: Codable, Identifiable {
    let id: String
    var title: String
    var taskType: MWTaskType?
    var status: String
    var version: Int
    var isPinned: Bool
    let createdAt: String
    var updatedAt: String?

    var resolvedTaskType: MWTaskType {
        taskType ?? .chat
    }

    var lastActivityAt: String {
        updatedAt ?? createdAt
    }

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
    let taskType: MWTaskType?
    let status: String
    let currentState: [String: AnyCodable]
    let version: Int
    let isPinned: Bool
    let createdAt: String
    let assistantReply: String?
    let pdfUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version
        case taskType = "task_type"
        case currentState = "current_state"
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
    let taskType: MWTaskType?
    let status: String
    let version: Int
    let isPinned: Bool
    let createdAt: String
    let updatedAt: String
    let messages: [MWMessage]
    let currentState: [String: AnyCodable]

    var resolvedTaskType: MWTaskType {
        taskType ?? inferMWTaskType(from: currentState)
    }

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
    let taskType: MWTaskType?
    let pdfUrl: String?
    let tokenUsage: MWTokenUsage?

    enum CodingKeys: String, CodingKey {
        case version
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
        case currentState = "current_state"
        case taskType = "task_type"
        case pdfUrl = "pdf_url"
        case tokenUsage = "token_usage"
    }
}

struct MWTokenUsage: Codable {
    let promptTokens: Int?
    let completionTokens: Int?
    let totalTokens: Int?
    let costDollars: Double?
    let model: String?
    let estimated: Bool?

    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case costDollars = "cost_dollars"
        case model, estimated
    }

    /// Formatted display string, e.g. "1.2k tok · $0.0012"
    var displayText: String? {
        let total = totalTokens ?? ((promptTokens ?? 0) + (completionTokens ?? 0))
        guard total > 0 else { return nil }
        let tokStr = total >= 1000 ? String(format: "%.1fk", Double(total) / 1000.0) : "\(total)"
        let prefix = (estimated == true) ? "~" : ""
        if let cost = costDollars, cost > 0 {
            return "\(prefix)\(tokStr) tok · $\(String(format: "%.4f", cost))"
        }
        return "\(prefix)\(tokStr) tok"
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
    let initialMessage: String?
    enum CodingKeys: String, CodingKey {
        case title
        case initialMessage = "initial_message"
    }
}


struct MWPinRequest: Codable {
    let pinned: Bool
}

struct MWRevertRequest: Codable {
    let version: Int
}

struct MWFinalizeResponse: Codable {
    let threadId: String
    let status: String
    let version: Int
    let pdfUrl: String?
    let linkedOfferLetterId: String?

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case status, version
        case pdfUrl = "pdf_url"
        case linkedOfferLetterId = "linked_offer_letter_id"
    }
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
