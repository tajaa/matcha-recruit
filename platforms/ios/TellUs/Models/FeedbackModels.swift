import Foundation

// Mirrors client/tellus/src/api/types.ts:159-197.

struct Report: Codable, Identifiable {
    let id: String
    let brand_id: String
    let store_id: String?
    let store_name: String?
    let report_number: String?
    let category: ReportCategory
    let sentiment: Sentiment
    let title: String?
    let description: String?
    let occurred_at: String?
    let reporter_contact: String?
    let usefulness_score: Int
    let status: ReportStatus
    let ai_summary: String?
    /// Open set — visible|flagged|removed today.
    let moderation_status: String
    let reward_status: RewardStatus?
    let points_awarded: Int
    let created_at: String
    let media: [ReportMedia]
    let rating: Int?
    let review_state: ReviewState?
    let publish_at: String?
    let hearted_at: String?
    let brand_public_reply: String?
    let brand_public_reply_at: String?
    let is_identified: Bool
    let has_dm_thread: Bool
    let answers: [ReportAnswer]
}

struct FeedbackStats: Codable {
    let total: Int
    let new: Int
    let positive: Int
    let neutral: Int
    let negative: Int
    let by_category: [String: Int]
}

struct RewardDecision: Encodable { let approve: Bool }
struct StatusPatch: Encodable { let status: String }
struct ReplyPut: Encodable { let body: String }
