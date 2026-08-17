import Foundation

/// Server-extendable string enums decode via this fallback so a new value
/// added on the backend degrades to `.unknown` instead of failing the whole
/// array decode. Closed sets (AccountType, ReviewState, MediaType,
/// ListingVisibility, Sentiment, ReportStatus) decode plainly — they're
/// fixed sets in the Pydantic Literal types, not DB-driven open sets.
protocol FallbackDecodable: RawRepresentable, Codable where RawValue == String {
    static var unknown: Self { get }
}

extension FallbackDecodable {
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: raw) ?? .unknown
    }
}

enum AccountType: String, Codable {
    case consumer, brand
}

enum BrandPlanStatus: String, Codable, FallbackDecodable {
    case pending, active, past_due, canceled, unknown
}

/// 'published' is derived server-side (held + past its 48h hold) — it never
/// appears in the DB, only in API responses.
enum ReviewState: String, Codable {
    case held, published, withdrawn
}

enum ReportCategory: String, Codable, CaseIterable, FallbackDecodable {
    case service, cleanliness, facilities, safety, compliment, other, unknown
}

enum Sentiment: String, Codable, CaseIterable {
    case positive, neutral, negative
}

enum ReportStatus: String, Codable, CaseIterable {
    case new, reviewing, resolved, archived
}

enum MediaType: String, Codable {
    case photo, video
}

enum RedemptionType: String, Codable, FallbackDecodable {
    case code, qr, manual, unknown
}

enum RedemptionStatus: String, Codable, FallbackDecodable {
    case pending, issued, redeemed, expired, cancelled, unknown
}

enum RewardStatus: String, Codable, FallbackDecodable {
    case pending, approved, rejected, unknown
}

enum BoardPostKind: String, Codable, CaseIterable, FallbackDecodable {
    case update, deal, event, question, promo, unknown
}

enum BoardReplyStatus: String, Codable, FallbackDecodable {
    case held, approved, rejected, removed, unknown
}

enum BoardMembershipStatus: String, Codable, FallbackDecodable {
    case pending, approved, declined, removed, left, cancelled, unknown
}

enum ListingVisibility: String, Codable {
    case `public`, board
}

enum BoardViewerRole: String, Codable, FallbackDecodable {
    case member, moderator, owner, admin, location_manager, staff, unknown
}

enum FriendshipStatus: String, Codable, FallbackDecodable {
    case none, pending_out, pending_in, friends, blocked, blocked_by, unknown
}

enum FriendActivityKind: String, Codable, FallbackDecodable {
    case review_published, place_followed, unknown
}

enum ProfileVisibility: String, Codable, CaseIterable, FallbackDecodable {
    case everyone, friends, `private`, unknown
}

enum FriendRequestDirection: String, Codable {
    case incoming, outgoing
}

enum FriendReportReason: String, Codable, CaseIterable, FallbackDecodable {
    case spam, harassment, impersonation, inappropriate, other, unknown
}
