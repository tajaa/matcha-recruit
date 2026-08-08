import Foundation

// Mirrors client/tellus/src/api/types.ts:398-424 and
// server/app/tellus/models/tellus.py:648-692 (routes/dms.py).

enum DmSenderRole: String, Codable, FallbackDecodable { case brand, consumer, unknown }

struct DmThread: Codable, Identifiable, Hashable {
    let id: String
    let report_id: String
    let counterparty_name: String
    let report_title: String?
    let report_number: String?
    let review_state: ReviewState?
    let publish_at: String?
    let blocked: Bool
    let unread_count: Int
    let last_message_at: String
    let created_at: String
}

struct DmMessage: Codable, Identifiable {
    let id: String
    let thread_id: String
    let sender_role: DmSenderRole
    let body: String
    let created_at: String
    let is_mine: Bool
}

struct DmSend: Encodable { let body: String }   // ≤4000 chars, server-enforced
