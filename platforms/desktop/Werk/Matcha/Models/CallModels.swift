import Foundation

/// Join policy for a channel audio call, picked by the owner at start time.
/// `inviteOnly`: only invited members may join. `members`: any channel member
/// may join until the room is full (4).
enum CallMode: String, Codable {
    case inviteOnly = "invite_only"
    case members
}

struct CallStartResponse: Codable {
    let callId: String
    let liveKitUrl: String
    let token: String
    let room: String
    let mode: String
    let maxParticipants: Int?
    let maxDurationSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case callId = "call_id"
        case liveKitUrl = "livekit_url"
        case token
        case room
        case mode
        case maxParticipants = "max_participants"
        case maxDurationSeconds = "max_duration_seconds"
    }
}

struct CallTokenResponse: Codable {
    let liveKitUrl: String
    let token: String
    let room: String
    let mode: String
    let elapsedSeconds: Int?
    let maxParticipants: Int?

    enum CodingKeys: String, CodingKey {
        case liveKitUrl = "livekit_url"
        case token
        case room
        case mode
        case elapsedSeconds = "elapsed_seconds"
        case maxParticipants = "max_participants"
    }
}

struct CallStatusResponse: Codable {
    let active: Bool
    let callId: String?
    let mode: String?
    let startedBy: String?
    let startedAt: String?
    let elapsedSeconds: Int?
    let participantIds: [String]?
    let invitedUserIds: [String]?
    let maxParticipants: Int?

    enum CodingKeys: String, CodingKey {
        case active
        case callId = "call_id"
        case mode
        case startedBy = "started_by"
        case startedAt = "started_at"
        case elapsedSeconds = "elapsed_seconds"
        case participantIds = "participant_ids"
        case invitedUserIds = "invited_user_ids"
        case maxParticipants = "max_participants"
    }
}

/// Active-call record kept in CallService.activeCalls, keyed by channelId.
/// Drives the "Call · n/4" pill and the join banner in the channel view.
/// Populated by WS call.started events AND a REST poll on channel-view appear.
struct ActiveCallInfo: Equatable {
    let callId: String
    let startedBy: String
    let startedAt: String
    let mode: CallMode
    var participantIds: [String]
    var invitedUserIds: [String]
}

struct WSCallStarted {
    let channelId: String
    let callId: String
    let startedBy: String
    let startedAt: String
    let mode: String
}

struct WSCallEnded {
    let channelId: String
    let callId: String
}

struct WSCallInvited {
    let channelId: String
    let callId: String
    let invitedBy: String
}

struct WSCallParticipantsChanged {
    let channelId: String
    let callId: String
    let participantIds: [String]
}
