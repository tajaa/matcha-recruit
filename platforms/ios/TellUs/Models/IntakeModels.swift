import Foundation

// Mirrors client/tellus/src/api/types.ts:106-149; payload semantics from
// client/tellus/src/pages/Intake.tsx:120-178.

struct IntakePrompt: Codable, Identifiable { let id: String; let prompt: String }

struct IntakeConfig: Codable {
    let brand_name: String
    let brand_logo_url: String?
    let store_name: String?
    /// Open set — server sends 6 categories today.
    let categories: [String]
    let prompts: [IntakePrompt]
    let claimed: Bool
}

struct MediaPresignRequest: Encodable {
    let media_type: String // "photo" | "video"
    let mime_type: String
    let file_size: Int
    let original_filename: String
}

struct MediaPresignResponse: Codable {
    let upload_url: String
    let storage_path: String
    let expires_in: Int
}

struct SubmittedMedia: Codable {
    /// Must keep the server's s3://…/tellus/ prefix verbatim.
    let storage_path: String
    let media_type: String
    let mime_type: String?
    let file_size: Int?
    let original_filename: String?
}

struct IntakeAnswerOut: Encodable { let prompt_id: String; let answer: String }

struct IntakeSubmission: Encodable {
    let category: String
    let sentiment: String
    let title: String?
    let description: String
    /// nil in-app — identity comes from the bearer token.
    let reporter_contact: String?
    let rating: Int?
    let post_as_review: Bool
    let media_keys: [SubmittedMedia]
    /// Honeypot — ALWAYS "". A non-empty value silently produces a fake
    /// success response server-side (bot trap), never a visible error.
    let website: String
    let answers: [IntakeAnswerOut]
}

struct FeedbackSubmitResponse: Codable {
    let report_id: String
    let report_number: String?
    let points_awarded: Int
    let earned: Bool
    let reward_pending: Bool
    let public_review: Bool
    let publish_at: String?
}
