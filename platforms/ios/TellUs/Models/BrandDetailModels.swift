import Foundation

// Mirrors server/app/tellus/models/tellus.py TellusPublicReview /
// TellusPublicBrandPage. Only the fields BrandDetailView renders are
// declared — JSONDecoder ignores the rest (media/answers/older reviews/etc.).

struct TellusPublicReview: Codable, Identifiable {
    let id: String
    let rating: Int
    let title: String?
    let description: String?
    let reviewer_name: String
    let store_name: String?
    let hearted: Bool
    let brand_reply: String?
    let like_count: Int
    let liked_by_me: Bool
}

struct TellusPublicBrandPage: Codable {
    let brand_name: String
    let slug: String
    let logo_url: String?
    let review_count: Int
    let avg_rating: Double?
    let reviews: [TellusPublicReview]
    let claimed: Bool
    let intake_token: String?
    let address: String?
    let city: String?
    let state: String?
    let has_board: Bool
    let messaging_enabled: Bool
    let followed: Bool
    // Phase 1 (profiles + invite). All decoded tolerantly (decodeIfPresent)
    // so a response from a server predating these fields still decodes.
    let tagline: String?
    let description: String?
    let cover_url: String?
    let category: String?
    let website: String?
    let hours: [String: String]?
    let invite_count: Int
    let invited_by_me: Bool

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        brand_name = try c.decode(String.self, forKey: .brand_name)
        slug = try c.decode(String.self, forKey: .slug)
        logo_url = try c.decodeIfPresent(String.self, forKey: .logo_url)
        review_count = try c.decodeIfPresent(Int.self, forKey: .review_count) ?? 0
        avg_rating = try c.decodeIfPresent(Double.self, forKey: .avg_rating)
        reviews = try c.decodeIfPresent([TellusPublicReview].self, forKey: .reviews) ?? []
        claimed = try c.decodeIfPresent(Bool.self, forKey: .claimed) ?? true
        intake_token = try c.decodeIfPresent(String.self, forKey: .intake_token)
        address = try c.decodeIfPresent(String.self, forKey: .address)
        city = try c.decodeIfPresent(String.self, forKey: .city)
        state = try c.decodeIfPresent(String.self, forKey: .state)
        has_board = try c.decodeIfPresent(Bool.self, forKey: .has_board) ?? false
        messaging_enabled = try c.decodeIfPresent(Bool.self, forKey: .messaging_enabled) ?? false
        followed = try c.decodeIfPresent(Bool.self, forKey: .followed) ?? false
        tagline = try c.decodeIfPresent(String.self, forKey: .tagline)
        description = try c.decodeIfPresent(String.self, forKey: .description)
        cover_url = try c.decodeIfPresent(String.self, forKey: .cover_url)
        category = try c.decodeIfPresent(String.self, forKey: .category)
        website = try c.decodeIfPresent(String.self, forKey: .website)
        hours = try c.decodeIfPresent([String: String].self, forKey: .hours)
        invite_count = try c.decodeIfPresent(Int.self, forKey: .invite_count) ?? 0
        invited_by_me = try c.decodeIfPresent(Bool.self, forKey: .invited_by_me) ?? false
    }
}
