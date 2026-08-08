import Foundation

/// Mirrors server/app/cappe/models/engage.py's messages/clients/reviews
/// shapes + client/src/cappe/types.ts:628-714. Phase 5 (Inbox, Clients,
/// Reviews).

// MARK: - Messages / threads

struct CappeMessage: Codable, Identifiable, Equatable {
    let id: String
    let thread_id: String
    let sender: String  // "owner" | "client"
    let body: String
    let created_at: String
}

struct CappeThread: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    let client_email: String
    let client_name: String?
    let subject: String?
    var status: String
    let booking_id: String?
    let order_id: String?
    var owner_unread: Int = 0
    let last_message_at: String
    let created_at: String
    let last_snippet: String?
}

/// `CappeThreadDetail` in the server is `CappeThread` + `access_token` +
/// `messages` (Pydantic inheritance) — flattened into one independent struct
/// here, matching how CappeReadiness/CappeReadinessItem are already two
/// separate structs rather than a subclass relationship.
struct CappeThreadDetail: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    let client_email: String
    let client_name: String?
    let subject: String?
    var status: String
    let booking_id: String?
    let order_id: String?
    var owner_unread: Int = 0
    let last_message_at: String
    let created_at: String
    let last_snippet: String?
    let access_token: String
    var messages: [CappeMessage] = []
}

struct CappeThreadCreate: Encodable {
    var client_email: String
    var client_name: String?
    var subject: String?
    var body: String
    var booking_id: String?
    var order_id: String?
}

struct CappeMessageCreate: Encodable {
    var body: String
}

// MARK: - Clients

struct CappeClient: Codable, Identifiable, Equatable {
    // email is the natural key — matches the delete-by-email endpoint.
    var id: String { email }
    let email: String
    let name: String?
    let phone: String?
    let orders_count: Int
    let bookings_count: Int
    let is_subscriber: Bool
    let has_thread: Bool
    let is_imported: Bool
    let total_spent_cents: Int
    let last_activity: String?
    let location_id: String?
    let location_name: String?
}

struct CappeClientCreate: Encodable {
    var email: String
    var name: String?
    var phone: String?
    var location_id: String?
    var notes: String?
    /// nil = leave the client's existing tags/location unchanged server-side
    /// (`CappeClientCreate.tags`/`location_id` in engage.py — both COALESCE
    /// against the stored row rather than overwrite). `[]` would still wipe
    /// tags to empty, so callers that don't edit tags must pass nil, not [].
    var tags: [String]? = nil
    var add_to_newsletter: Bool = false
}

// MARK: - Reviews

struct CappeReview: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    let author_name: String
    let rating: Int?
    let body: String
    var status: String
    let created_at: String
}

struct CappeReviewModerate: Encodable {
    var status: String  // approved|hidden|pending
}
