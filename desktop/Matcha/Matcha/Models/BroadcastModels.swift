import Foundation

struct BroadcastStartResponse: Codable {
    let broadcastId: String
    let liveKitUrl: String
    let token: String
    let room: String
    let maxDurationSeconds: Int?
    let weeklyRemaining: Int?

    enum CodingKeys: String, CodingKey {
        case broadcastId = "broadcast_id"
        case liveKitUrl = "livekit_url"
        case token
        case room
        case maxDurationSeconds = "max_duration_seconds"
        case weeklyRemaining = "weekly_remaining"
    }
}

struct BroadcastTokenResponse: Codable {
    let liveKitUrl: String
    let token: String
    let room: String
    let maxDurationSeconds: Int?
    let elapsedSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case liveKitUrl = "livekit_url"
        case token
        case room
        case maxDurationSeconds = "max_duration_seconds"
        case elapsedSeconds = "elapsed_seconds"
    }
}

struct BroadcastStatusResponse: Codable {
    let active: Bool
    let broadcastId: String?
    let startedAt: String?
    let startedBy: String?
    let title: String?
    let publisherUserIds: [String]?
    let elapsedSeconds: Int?
    let maxDurationSeconds: Int?
    let weeklyLimit: Int?
    let weeklyUsed: Int?
    let weeklyRemaining: Int?

    enum CodingKeys: String, CodingKey {
        case active
        case broadcastId = "broadcast_id"
        case startedAt = "started_at"
        case startedBy = "started_by"
        case title
        case publisherUserIds = "publisher_user_ids"
        case elapsedSeconds = "elapsed_seconds"
        case maxDurationSeconds = "max_duration_seconds"
        case weeklyLimit = "weekly_limit"
        case weeklyUsed = "weekly_used"
        case weeklyRemaining = "weekly_remaining"
    }
}

/// WS envelope received when a broadcast starts (also sent retroactively to late joiners)
struct WSBroadcastStarted {
    let channelId: String
    let broadcastId: String
    let startedBy: String
    let startedAt: String
    let title: String?
}

struct WSBroadcastEnded {
    let channelId: String
    let broadcastId: String
}

struct WSBroadcastPublisherChanged {
    let channelId: String
    let userId: String
    let canPublish: Bool
}

struct WSBroadcastTokenGrant {
    let channelId: String
    let token: String
    let liveKitUrl: String
    let canPublish: Bool
}
