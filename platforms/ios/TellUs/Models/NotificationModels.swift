import Foundation

/// Mirrors client/tellus/src/api/types.ts:607-616. `kind` is an open set —
/// 13 known values today, decoded as a plain String so a new server kind
/// never fails decode; icon mapping falls back to a generic bell.
struct TellusNotification: Codable, Identifiable {
    let id: String
    let kind: String
    let title: String
    let body: String?
    let reference_type: String?
    let reference_id: String?
    let is_read: Bool
    let created_at: String
}

enum NotificationKind {
    static let known: Set<String> = [
        "points_earned", "level_up", "badge", "redemption", "points_adjustment",
        "feedback", "dm_message", "board_join_request", "board_post",
        "board_reply_pending", "board_reply_approved", "membership_approved", "board_team_added",
    ]
}
