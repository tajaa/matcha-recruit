import Foundation

// Mirrors server/app/tellus/models/tellus.py TellusDiscoverEntry / TellusDiscoverPage.

enum DiscoverSource: String, Codable {
    case tellus, google
}

struct DiscoverEntry: Codable, Identifiable, Hashable {
    let source: DiscoverSource
    let name: String
    let slug: String?
    let google_place_id: String?
    let logo_url: String?
    let city: String?
    let state: String?
    let address: String?
    let distance_km: Double?
    let category_label: String?
    let rating: Double?
    let review_count: Int
    let rating_count: Int
    let claimed: Bool
    let has_board: Bool
    var followed: Bool
    let messaging_enabled: Bool
    let intake_token: String?

    /// Google rows have no slug, and two brands can share a name — fall back
    /// through place_id before name so identity is still stable enough for
    /// SwiftUI diffing.
    var id: String { slug ?? google_place_id ?? name }
}

struct DiscoverPage: Codable {
    let entries: [DiscoverEntry]
    let total: Int
    let next_offset: Int?
    let google_attribution: Bool
}
