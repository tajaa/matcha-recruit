import Foundation

// MARK: - Inbox

struct MWInboxConversation: Codable, Identifiable {
    let id: String
    var title: String?
    let isGroup: Bool?
    var lastMessageAt: String?
    var lastMessagePreview: String?
    var participants: [MWInboxParticipant]?
    var unreadCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, participants
        case isGroup = "is_group"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case unreadCount = "unread_count"
    }
}

struct MWInboxConversationDetail: Codable, Identifiable {
    let id: String
    var title: String?
    let isGroup: Bool?
    let createdBy: String?
    var lastMessageAt: String?
    var lastMessagePreview: String?
    var participants: [MWInboxParticipant]?
    var messages: [MWInboxMessage]?
    var unreadCount: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, participants, messages
        case isGroup = "is_group"
        case createdBy = "created_by"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case unreadCount = "unread_count"
        case createdAt = "created_at"
    }
}

struct MWInboxMessage: Codable, Identifiable {
    let id: String
    let conversationId: String
    let senderId: String
    let senderName: String
    let content: String
    let attachments: [MWInboxAttachment]?
    let createdAt: String
    let editedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, content, attachments
        case conversationId = "conversation_id"
        case senderId = "sender_id"
        case senderName = "sender_name"
        case createdAt = "created_at"
        case editedAt = "edited_at"
    }
}

struct MWInboxAttachment: Codable, Identifiable {
    var id: String { url }
    let url: String
    let filename: String
    let contentType: String
    let size: Int

    enum CodingKeys: String, CodingKey {
        case url, filename, size
        case contentType = "content_type"
    }

    var isImage: Bool { contentType.hasPrefix("image/") }
}

struct MWInboxParticipant: Codable, Identifiable {
    var id: String { userId }
    let userId: String
    let name: String
    let email: String
    let role: String?
    let avatarUrl: String?
    let lastReadAt: String?
    let isMuted: Bool?

    enum CodingKeys: String, CodingKey {
        case name, email, role
        case userId = "user_id"
        case avatarUrl = "avatar_url"
        case lastReadAt = "last_read_at"
        case isMuted = "is_muted"
    }
}

struct MWInboxUserSearch: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let role: String?
    let avatarUrl: String?
    let companyName: String?

    enum CodingKeys: String, CodingKey {
        case id, email, name, role
        case avatarUrl = "avatar_url"
        case companyName = "company_name"
    }
}
