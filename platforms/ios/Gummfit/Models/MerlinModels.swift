import Foundation

struct CappeMerlinHistoryTurn: Codable {
    let role: String
    let content: String
    let ops_summary: String?
}

struct CappeMerlinAttachment: Codable {
    let url: String
    let mime: String?
}

struct CappeMerlinSelection: Codable {
    let block: String
    let field: String?
    let element: String?
    let kind: String
    let start: Int?
    let end: Int?
    let text: String?
}

struct CappeMerlinChatRequest: Encodable {
    let page_id: String
    let conversation_id: String?
    let message: String
    let history: [CappeMerlinHistoryTurn]
    let blocks: [CappeBlock]
    let theme: [String: JSONValue]
    let model_tier: String
    let selected_block: String?
    let selection: CappeMerlinSelection?
    let attachments: [CappeMerlinAttachment]
}

struct CappeMerlinSetupRequest: Encodable {
    let conversation_id: String?
    let message: String
}

enum CappeMerlinFrame: Decodable {
    case status(String)
    case step(CappeMerlinStep)
    case stagedAction(CappeSetupActionEntry)
    case error(String)
    case result(CappeMerlinResult)
    case setupResult(CappeSetupResult)
    case unknown

    private enum CodingKeys: String, CodingKey { case type, message, data, action }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        switch try container.decodeIfPresent(String.self, forKey: .type) {
        case "status": self = .status(try container.decode(String.self, forKey: .message))
        case "step": self = .step(try CappeMerlinStep(from: decoder))
        case "staged_action": self = .stagedAction(try container.decode(CappeSetupActionEntry.self, forKey: .action))
        case "error": self = .error(try container.decode(String.self, forKey: .message))
        case "result":
            let data = try container.decode(JSONValue.self, forKey: .data)
            let encoded = try JSONEncoder().encode(data)
            if data.objectValue?["ops"] != nil {
                self = .result(try JSONDecoder().decode(CappeMerlinResult.self, from: encoded))
            } else {
                self = .setupResult(try JSONDecoder().decode(CappeSetupResult.self, from: encoded))
            }
        default: self = .unknown
        }
    }
}

struct CappeMerlinStep: Codable, Identifiable {
    let id: String
    let kind: String
    let label: String
    let results: [CappeMerlinOpResult]?
    let image_url: String?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        kind = try container.decodeIfPresent(String.self, forKey: .kind) ?? ""
        label = try container.decodeIfPresent(String.self, forKey: .label) ?? ""
        results = try container.decodeIfPresent([CappeMerlinOpResult].self, forKey: .results)
        image_url = try container.decodeIfPresent(String.self, forKey: .image_url)
    }

    private enum CodingKeys: String, CodingKey { case id, kind, label, results, image_url }
}

struct CappeMerlinResult: Decodable {
    let message: String
    let ops: [JSONValue]
    let rejected: [CappeMerlinRejection]
    let tier: String
    let routed: Bool
    let conversation_id: String?
    let message_id: String?
    let steps: [CappeMerlinStep]?
}

struct CappeSetupResult: Decodable {
    let message: String
    let links: [JSONValue]?
    let tier: String
    let steps: [CappeMerlinStep]?
    let results: [JSONValue]?
    let readiness: [String: JSONValue]?
}

struct CappeMerlinRejection: Codable {
    let op: [String: JSONValue]
    let reason: String
}

struct CappeMerlinOpResult: Codable {
    let ok: Bool
    let summary: String
}

struct CappeMerlinConversation: Codable, Identifiable {
    let id: String
    let title: String
    let created_at: String
    let updated_at: String
}

struct CappeMerlinStoredMessage: Codable, Identifiable {
    let id: String
    let role: String
    let content: String
    let results: [CappeMerlinOpResult]?
    let steps: [CappeMerlinStep]?
    let attachments: [JSONValue]?
    let ops: [JSONValue]?
    let tier: String?
    let created_at: String

    var isUnapplied: Bool { ops != nil && results == nil }
}

struct CappeMerlinConversationDetail: Codable {
    let id: String
    let title: String
    let created_at: String
    let updated_at: String
    let kind: String
    let messages: [CappeMerlinStoredMessage]
    let staged_actions: [CappeSetupActionEntry]?
}

struct CappeSetupActionEntry: Codable, Identifiable {
    let id: String
    let type: String
    let summary: String
    let payload: [String: JSONValue]
    let status: String
    let result: [String: JSONValue]?
    let message: String?
    let created_at: String
    let executed_at: String?
}

struct CappeSetupActionResult: Codable {
    let action: CappeSetupActionEntry
    let message: String
    let readiness: [String: JSONValue]
}

struct CappeMerlinResultsUpdate: Encodable {
    let results: [CappeMerlinOpResult]
}
