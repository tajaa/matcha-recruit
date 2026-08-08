import Foundation

/// Mirrors `Literal["business","personal","creator"]`
/// (server/app/cappe/models/auth.py:17). Open-set with `.unknown` fallback —
/// a server-added case must never crash decode on an older client build.
/// SINGLE-VALUED per account (never both owner+creator — see plan §Context).
enum AccountType: String, Codable {
    case business
    case personal
    case creator
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = AccountType(rawValue: raw) ?? .unknown
    }
}

/// Mirrors `CappeSiteStatus = 'draft' | 'published' | 'archived'`
/// (client/src/cappe/types.ts:50).
enum SiteStatus: String, Codable {
    case draft
    case published
    case archived
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SiteStatus(rawValue: raw) ?? .unknown
    }
}

// The remaining open-set enums (OrderStatus, BookingStatus, CampaignStatus,
// OfferStatus, DeliverableStatus, PaymentStatus, CreatorProfileStatus,
// Fulfillment) land with their owning model files in later phases
// (Catalog/Orders/Bookings/Collab/Creator) — see GUMMFIT_IOS_APP_PLAN.md §2.
