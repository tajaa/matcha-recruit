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
    /// User IDs the server resolved from @mentions in `content`. Only populated
    /// on broadcasts from the live channels WS — older REST-fetched messages
    /// won't carry this; renderers may still parse @handle patterns from
    /// `content` for display.
    let mentionedUserIds: [String]?

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
        case mentionedUserIds = "mentioned_user_ids"
    }

    init(id: String, channelId: String, senderId: String, senderName: String,
         senderAvatarUrl: String?, content: String, attachments: [ChannelAttachment],
         replyToId: String? = nil, replyPreview: ReplyPreview? = nil,
         reactions: [ChannelReaction] = [],
         createdAt: String, editedAt: String?,
         mentionedUserIds: [String]? = nil) {
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
        self.mentionedUserIds = mentionedUserIds
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
        self.mentionedUserIds = try? c.decodeIfPresent([String].self, forKey: .mentionedUserIds)
    }
}

/// Channel categories — single source of truth on the client. Mirrors the
/// `CHANNEL_CATEGORIES` tuple in `server/app/core/routes/channels.py`. Update
/// both sides when adding.
enum ChannelCategory: String, CaseIterable, Identifiable {
    case general
    case engineering
    case design
    case sales
    case support
    case operations
    case marketing
    case hr
    case announcements

    var id: String { rawValue }

    var label: String {
        switch self {
        case .general: return "General"
        case .engineering: return "Engineering"
        case .design: return "Design"
        case .sales: return "Sales"
        case .support: return "Support"
        case .operations: return "Operations"
        case .marketing: return "Marketing"
        case .hr: return "HR"
        case .announcements: return "Announcements"
        }
    }
}

struct ChannelSummary: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let slug: String
    let description: String?
    let visibility: String
    let category: String?
    let isPaid: Bool
    let priceCents: Int?
    let currency: String?
    let memberCount: Int
    var unreadCount: Int
    let lastMessageAt: String?
    let lastMessagePreview: String?
    let isMember: Bool
    let myRole: String?
    /// Set when this channel is the auto-created discussion channel for a
    /// matcha-work collab project. Sidebar renders a "collab" badge.
    let projectId: String?
    let projectTitle: String?

    enum CodingKeys: String, CodingKey {
        case id, name, slug, description, visibility, category
        case isPaid = "is_paid"
        case priceCents = "price_cents"
        case currency
        case memberCount = "member_count"
        case unreadCount = "unread_count"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case isMember = "is_member"
        case myRole = "my_role"
        case projectId = "project_id"
        case projectTitle = "project_title"
    }
}

struct ChannelDetail: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let slug: String
    let description: String?
    let visibility: String
    let category: String?
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
        case id, name, slug, description, visibility, category, currency, members, messages
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
