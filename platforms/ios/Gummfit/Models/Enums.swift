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

/// Mirrors `Fulfillment = Literal["physical","digital","service","booking"]`
/// (server/app/cappe/models/shop.py:14).
enum Fulfillment: String, Codable {
    case physical
    case digital
    case service
    case booking
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Fulfillment(rawValue: raw) ?? .unknown
    }

    /// `.unknown` came from a server value this build doesn't recognize —
    /// re-encoding it literally as `"unknown"` would 422 against the
    /// server's `Literal[...]` field, so callers building a write body must
    /// omit the field entirely when this is false.
    var isWritable: Bool { self != .unknown }
}

/// Mirrors `CappeOrder.status` (server/app/cappe/models/shop.py:162,205) —
/// "pending","paid","fulfilled","cancelled","refunded" are the PATCH-able set;
/// "declined" is a server-only terminal state (order-decline endpoint).
enum OrderStatus: String, Codable {
    case pending
    case paid
    case fulfilled
    case cancelled
    case refunded
    case declined
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = OrderStatus(rawValue: raw) ?? .unknown
    }
}

/// Mirrors `CappeBookingStatusUpdate.status` (server/app/cappe/models/bookings.py:270)
/// plus the server-only terminal "declined" state (booking-decline endpoint).
enum BookingStatus: String, Codable {
    case pending
    case confirmed
    case cancelled
    case completed
    case declined
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = BookingStatus(rawValue: raw) ?? .unknown
    }
}

/// Mirrors `DiscountScope = Literal["all","booking_type","product"]`
/// (server/app/cappe/models/shop.py:287).
enum DiscountScope: String, Codable {
    case all
    case booking_type
    case product
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = DiscountScope(rawValue: raw) ?? .unknown
    }
}

// The remaining open-set enums (CampaignStatus, OfferStatus, DeliverableStatus,
// PaymentStatus, CreatorProfileStatus) land with their owning model files in
// later phases (Collab/Creator/Billing) — see GUMMFIT_IOS_APP_PLAN.md §2.
