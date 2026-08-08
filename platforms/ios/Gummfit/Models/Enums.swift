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

    /// True for both storefront personas (org or solo pro) — routes to the
    /// owner tab surface. `creator` routes to the creator tab surface.
    var isOwner: Bool { self == .business || self == .personal }
}

// The remaining open-set enums (OrderStatus, BookingStatus, CampaignStatus,
// OfferStatus, DeliverableStatus, PaymentStatus, CreatorProfileStatus,
// Fulfillment, SiteStatus) land with their owning model files in later
// phases (Sites/Catalog/Orders/Bookings/Collab/Creator) — see
// GUMMFIT_IOS_APP_PLAN.md §2.
