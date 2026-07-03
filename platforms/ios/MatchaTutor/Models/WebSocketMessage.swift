import Foundation

enum WSMessageType: String, Codable {
    case user
    case assistant
    case status
    case system
}

struct WSMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let type: WSMessageType
    let content: String
    let timestamp: TimeInterval

    init(type: WSMessageType, content: String, timestamp: TimeInterval = Date().timeIntervalSince1970 * 1000) {
        self.id = UUID()
        self.type = type
        self.content = content
        self.timestamp = timestamp
    }

    enum CodingKeys: String, CodingKey {
        case type, content, timestamp
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.type = try container.decode(WSMessageType.self, forKey: .type)
        self.content = try container.decode(String.self, forKey: .content)
        self.timestamp = try container.decode(TimeInterval.self, forKey: .timestamp)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encode(content, forKey: .content)
        try container.encode(timestamp, forKey: .timestamp)
    }

    static func == (lhs: WSMessage, rhs: WSMessage) -> Bool {
        lhs.id == rhs.id
    }
}

// Audio binary protocol constants
enum AudioProtocol {
    static let clientAudioPrefix: UInt8 = 0x01
    static let serverAudioPrefix: UInt8 = 0x02

    // Audio configuration
    static let inputSampleRate: Double = 16000
    static let outputSampleRate: Double = 24000
    static let audioChunkSize: Int = 4096
}

// Session protection constants
enum SessionProtection {
    static let idleTimeoutSeconds: TimeInterval = 5 * 60        // 5 minutes
    static let warningBeforeDisconnectSeconds: TimeInterval = 60 // 1 minute warning
    static let defaultMaxSessionDurationSeconds: TimeInterval = 12 * 60 // 12 minutes
}
