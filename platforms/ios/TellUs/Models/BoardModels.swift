import Foundation

// Mirrors the board_* shapes in client/tellus/src/api/types.ts:623-733 and
// server/app/tellus/models/tellus.py.

struct BoardReply: Codable, Identifiable {
    let id: String
    let post_id: String
    let author_name: String
    let is_mine: Bool
    let status: BoardReplyStatus
    let body: String
    let created_at: String
}

struct BoardPost: Codable, Identifiable {
    let id: String
    let kind: BoardPostKind
    let title: String
    let body: String?
    /// Embedded for kind == .deal.
    let listing: Listing?
    let event_starts_at: String?
    let event_ends_at: String?
    let is_pinned: Bool
    let moderation_status: String
    let approved_reply_count: Int
    /// Present only for moderators.
    let held_reply_count: Int?
    let created_at: String
}

struct BoardPage: Codable {
    let board_id: String
    let brand_id: String
    let brand_name: String
    let brand_slug: String
    let logo_url: String?
    let title: String?
    let description: String?
    let is_active: Bool
    let plan_paused: Bool
    let viewer_role: BoardViewerRole
    let posts: [BoardPost]
    let total: Int
}

struct BoardMembership: Codable, Identifiable {
    let id: String
    let brand_id: String
    let brand_name: String
    let brand_slug: String
    let logo_url: String?
    let status: BoardMembershipStatus
    let requested_at: String
    let decided_at: String?
}

struct BoardJoinRequest: Codable, Identifiable {
    let id: String
    let account_display_name: String
    let note: String?
    let requested_at: String
    let review_count: Int
    let hearted: Bool
    let redemption_count: Int
}

struct BoardMemberEntry: Codable, Identifiable {
    let id: String
    let account_display_name: String
    let joined_at: String
}

/// GET /me/moderated-brands — bootstrap list for consumer moderators.
struct ModeratedBrand: Codable, Identifiable {
    let brand_id: String
    let name: String
    let slug: String
    let role: String // "owner" | "moderator"
    var id: String { brand_id }
}

struct BoardManageSummary: Codable {
    let board_id: String
    let title: String?
    let description: String?
    let is_active: Bool
    let pending_requests: Int
    let held_replies: Int
    let member_count: Int
    let viewer_role: BoardViewerRole
}

/// GET /board/manage/replies has no response_model on the server — shape
/// verified against server/app/tellus/routes/board.py:632-639's dict literal.
struct BoardManageReplyRow: Codable, Identifiable {
    let id: String
    let post_id: String
    let post_title: String
    let author_name: String
    let body: String
    let status: BoardReplyStatus
    let created_at: String
}

struct BoardPostCreate: Encodable {
    let kind: String
    let title: String
    let body: String?
    /// REQUIRED for kind == "deal"; must be a board-visibility listing owned
    /// by this brand. v1 UI omits the deal kind (no listing picker built).
    let listing_id: String?
    let event_starts_at: String?
    let event_ends_at: String?
}

struct BoardJoinBody: Encodable { let note: String? }
struct ReplyCreate: Encodable { let body: String }
