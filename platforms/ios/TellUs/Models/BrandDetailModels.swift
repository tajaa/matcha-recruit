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
    let city: String?
    let state: String?
    let has_board: Bool
    let messaging_enabled: Bool
    let followed: Bool
}
