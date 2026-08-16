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
    // Phase 1 (profiles + invite) — tellus rows only. Decoded via
    // decodeIfPresent below so a response from a server predating these
    // fields still decodes instead of throwing.
    let tagline: String?
    let cover_url: String?
    var invite_count: Int
    // Phase 2 (deals) — decoded the same tolerant way; false until the
    // deals migration lands server-side.
    let has_active_deal: Bool

    /// Google rows have no slug, and two brands can share a name — fall back
    /// through place_id before name so identity is still stable enough for
    /// SwiftUI diffing.
    var id: String { slug ?? google_place_id ?? name }

    /// Explicit memberwise init — writing a custom init(from:) below
    /// suppresses Swift's auto-generated memberwise initializer, and tests /
    /// call sites still construct DiscoverEntry directly (not just via
    /// decode). New Phase 1/2 fields default so existing call sites don't
    /// need updating.
    init(
        source: DiscoverSource, name: String, slug: String? = nil,
        google_place_id: String? = nil, logo_url: String? = nil, city: String? = nil,
        state: String? = nil, address: String? = nil, distance_km: Double? = nil,
        category_label: String? = nil, rating: Double? = nil, review_count: Int = 0,
        rating_count: Int = 0, claimed: Bool = false, has_board: Bool = false,
        followed: Bool = false, messaging_enabled: Bool = false, intake_token: String? = nil,
        tagline: String? = nil, cover_url: String? = nil, invite_count: Int = 0,
        has_active_deal: Bool = false
    ) {
        self.source = source
        self.name = name
        self.slug = slug
        self.google_place_id = google_place_id
        self.logo_url = logo_url
        self.city = city
        self.state = state
        self.address = address
        self.distance_km = distance_km
        self.category_label = category_label
        self.rating = rating
        self.review_count = review_count
        self.rating_count = rating_count
        self.claimed = claimed
        self.has_board = has_board
        self.followed = followed
        self.messaging_enabled = messaging_enabled
        self.intake_token = intake_token
        self.tagline = tagline
        self.cover_url = cover_url
        self.invite_count = invite_count
        self.has_active_deal = has_active_deal
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        source = try c.decode(DiscoverSource.self, forKey: .source)
        name = try c.decode(String.self, forKey: .name)
        slug = try c.decodeIfPresent(String.self, forKey: .slug)
        google_place_id = try c.decodeIfPresent(String.self, forKey: .google_place_id)
        logo_url = try c.decodeIfPresent(String.self, forKey: .logo_url)
        city = try c.decodeIfPresent(String.self, forKey: .city)
        state = try c.decodeIfPresent(String.self, forKey: .state)
        address = try c.decodeIfPresent(String.self, forKey: .address)
        distance_km = try c.decodeIfPresent(Double.self, forKey: .distance_km)
        category_label = try c.decodeIfPresent(String.self, forKey: .category_label)
        rating = try c.decodeIfPresent(Double.self, forKey: .rating)
        review_count = try c.decodeIfPresent(Int.self, forKey: .review_count) ?? 0
        rating_count = try c.decodeIfPresent(Int.self, forKey: .rating_count) ?? 0
        claimed = try c.decodeIfPresent(Bool.self, forKey: .claimed) ?? false
        has_board = try c.decodeIfPresent(Bool.self, forKey: .has_board) ?? false
        followed = try c.decodeIfPresent(Bool.self, forKey: .followed) ?? false
        messaging_enabled = try c.decodeIfPresent(Bool.self, forKey: .messaging_enabled) ?? false
        intake_token = try c.decodeIfPresent(String.self, forKey: .intake_token)
        tagline = try c.decodeIfPresent(String.self, forKey: .tagline)
        cover_url = try c.decodeIfPresent(String.self, forKey: .cover_url)
        invite_count = try c.decodeIfPresent(Int.self, forKey: .invite_count) ?? 0
        has_active_deal = try c.decodeIfPresent(Bool.self, forKey: .has_active_deal) ?? false
    }
}

struct DiscoverPage: Codable {
    let entries: [DiscoverEntry]
    let total: Int
    let next_offset: Int?
    let google_attribution: Bool
}

/// Share-sheet payload for a Discover invite — Identifiable so it can drive
/// a SwiftUI `.sheet(item:)`.
struct DiscoverShareItem: Identifiable {
    let url: URL
    let text: String
    var id: String { url.absoluteString }
}
