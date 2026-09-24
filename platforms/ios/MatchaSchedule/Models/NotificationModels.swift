import Foundation

struct ScheduleNotification: Decodable, Identifiable {
    let id: String
    let type: String
    let title: String
    let body: String?
    let link: String?
    let metadata: ScheduleNotificationMetadata?
    let is_read: Bool
    let created_at: String
}

struct ScheduleNotificationMetadata: Decodable {
    let request_id: String?
    let shift_id: String?
    let conversation_id: String?
}

struct NotificationsResponse: Decodable {
    let notifications: [ScheduleNotification]
    let total: Int
}
