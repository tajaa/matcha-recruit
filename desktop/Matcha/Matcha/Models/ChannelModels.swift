import Foundation

struct ChannelAttachment: Codable, Hashable {
    let url: String
    let filename: String
    let contentType: String
    let size: Int

    enum CodingKeys: String, CodingKey {
        case url, filename, size
        case contentType = "content_type"
    }
}

struct ChannelMember: Codable, Identifiable, Hashable {
    let userId: String
    let name: String
    let email: String
    let role: String
    let channelRole: String
    let avatarUrl: String?
    let joinedAt: String

    var id: String { userId }

    enum CodingKeys: String, CodingKey {
        case name, email, role
        case userId = "user_id"
        case channelRole = "channel_role"
        case avatarUrl = "avatar_url"
        case joinedAt = "joined_at"
    }
}

struct ChannelReaction: Codable, Hashable {
    let emoji: String
    let userIds: [String]
    let count: Int

    enum CodingKeys: String, CodingKey {
        case emoji, count
        case userIds = "user_ids"
    }
}

struct ReplyPreview: Codable, Hashable {
    let id: String
    let senderName: String
    let content: String
    let attachments: [ChannelAttachment]

    enum CodingKeys: String, CodingKey {
        case id, content, attachments
        case senderName = "sender_name"
    }

    init(id: String, senderName: String, content: String, attachments: [ChannelAttachment] = []) {
        self.id = id; self.senderName = senderName; self.content = content; self.attachments = attachments
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decode(String.self, forKey: .id)
        self.senderName = try c.decode(String.self, forKey: .senderName)
        self.content = try c.decode(String.self, forKey: .content)
        self.attachments = (try? c.decode([ChannelAttachment].self, forKey: .attachments)) ?? []
    }
}

struct ChannelMessage: Codable, Identifiable, Hashable {
    let id: String
    let channelId: String
    let senderId: String
    let senderName: String
    let senderAvatarUrl: String?
    let content: String
    let attachments: [ChannelAttachment]
    let replyToId: String?
    let replyPreview: ReplyPreview?
    var reactions: [ChannelReaction]
    let createdAt: String
    let editedAt: String?
    var deletedAt: String?
    var deletedBy: String?

    enum CodingKeys: String, CodingKey {
        case id, content, attachments, reactions
        case channelId = "channel_id"
        case senderId = "sender_id"
        case senderName = "sender_name"
        case senderAvatarUrl = "sender_avatar_url"
        case replyToId = "reply_to_id"
        case replyPreview = "reply_preview"
        case createdAt = "created_at"
        case editedAt = "edited_at"
        case deletedAt = "deleted_at"
        case deletedBy = "deleted_by"
    }

    init(id: String, channelId: String, senderId: String, senderName: String,
         senderAvatarUrl: String?, content: String, attachments: [ChannelAttachment],
         replyToId: String? = nil, replyPreview: ReplyPreview? = nil,
         reactions: [ChannelReaction] = [],
         createdAt: String, editedAt: String?) {
        self.id = id
        self.channelId = channelId
        self.senderId = senderId
        self.senderName = senderName
        self.senderAvatarUrl = senderAvatarUrl
        self.content = content
        self.attachments = attachments
        self.replyToId = replyToId
        self.replyPreview = replyPreview
        self.reactions = reactions
        self.createdAt = createdAt
        self.editedAt = editedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decode(String.self, forKey: .id)
        self.channelId = try c.decode(String.self, forKey: .channelId)
        self.senderId = try c.decode(String.self, forKey: .senderId)
        self.senderName = try c.decode(String.self, forKey: .senderName)
        self.senderAvatarUrl = try c.decodeIfPresent(String.self, forKey: .senderAvatarUrl)
        self.content = try c.decode(String.self, forKey: .content)
        self.attachments = (try? c.decode([ChannelAttachment].self, forKey: .attachments)) ?? []
        self.replyToId = try c.decodeIfPresent(String.self, forKey: .replyToId)
        self.replyPreview = try c.decodeIfPresent(ReplyPreview.self, forKey: .replyPreview)
        self.reactions = (try? c.decode([ChannelReaction].self, forKey: .reactions)) ?? []
        self.createdAt = try c.decode(String.self, forKey: .createdAt)
        self.editedAt = try c.decodeIfPresent(String.self, forKey: .editedAt)
    }
}

struct ChannelSummary: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let slug: String
    let description: String?
    let visibility: String
    let isPaid: Bool
    let memberCount: Int
    let unreadCount: Int
    let lastMessageAt: String?
    let lastMessagePreview: String?
    let isMember: Bool
    let myRole: String?

    enum CodingKeys: String, CodingKey {
        case id, name, slug, description, visibility
        case isPaid = "is_paid"
        case memberCount = "member_count"
        case unreadCount = "unread_count"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case isMember = "is_member"
        case myRole = "my_role"
    }
}

struct ChannelDetail: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let slug: String
    let description: String?
    let visibility: String
    let isPaid: Bool
    let priceCents: Int?
    let currency: String
    let isArchived: Bool
    let createdBy: String
    let createdAt: String
    let memberCount: Int
    let isMember: Bool
    let myRole: String?
    let members: [ChannelMember]
    let messages: [ChannelMessage]

    enum CodingKeys: String, CodingKey {
        case id, name, slug, description, visibility, currency, members, messages
        case isPaid = "is_paid"
        case priceCents = "price_cents"
        case isArchived = "is_archived"
        case createdBy = "created_by"
        case createdAt = "created_at"
        case memberCount = "member_count"
        case isMember = "is_member"
        case myRole = "my_role"
    }
}

struct UserConnection: Codable, Identifiable, Hashable {
    let userId: String
    let name: String
    let email: String
    let avatarUrl: String?
    let createdAt: String

    var id: String { userId }

    enum CodingKeys: String, CodingKey {
        case name, email
        case userId = "user_id"
        case avatarUrl = "avatar_url"
        case createdAt = "created_at"
    }
}

struct ChannelOnlineUser: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, name
        case avatarUrl = "avatar_url"
    }
}
