import Foundation

// Mirrors client/tellus/src/api/types.ts:111-116, 151-157, 301-325.

struct ReportMedia: Codable, Identifiable {
    let id: String
    let media_type: MediaType
    let mime_type: String?
    let original_filename: String?
    /// PRESIGNED, 15-minute TTL — minted fresh per response. Never persist
    /// this string; see MediaByteLoader, which caches bytes by `id` instead.
    let url: String?
}

struct ReportAnswer: Codable, Identifiable {
    let id: String
    let prompt_text: String
    let answer: String
    let position: Int
}

struct MyReview: Codable, Identifiable {
    let id: String
    let brand_name: String
    let brand_slug: String
    let store_name: String?
    let rating: Int?
    let title: String?
    let description: String?
    let review_state: ReviewState
    let publish_at: String
    let created_at: String
    let points_awarded: Int
    let hearted: Bool
    let brand_public_reply: String?
    let brand_public_reply_at: String?
    let dm_thread_id: String?
    let media: [ReportMedia]
    let answers: [ReportAnswer]
    let like_count: Int?
    let liked_by_me: Bool?
    var likeCount: Int { like_count ?? 0 }
    var likedByMe: Bool { liked_by_me ?? false }

    /// PATCH only valid while held and before publish_at — server 409s
    /// otherwise.
    var isEditable: Bool { review_state == .held }
}

struct MyReviewUpdate: Encodable {
    let title: String?
    let description: String?
    let rating: Int?
}
