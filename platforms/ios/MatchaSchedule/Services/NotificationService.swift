import Foundation

enum NotificationService {
    private static let root = "/matcha-work/notifications"
    private struct UnreadResponse: Decodable { let count: Int }
    private struct MarkReadBody: Encodable { let notification_ids: [String] }

    static func list() async throws -> NotificationsResponse {
        try await APIClient.shared.request(method: "GET", path: "\(root)?limit=50&offset=0")
    }

    static func unreadCount() async throws -> Int {
        let response: UnreadResponse = try await APIClient.shared.request(method: "GET", path: "\(root)/unread-count")
        return response.count
    }

    static func markRead(_ ids: [String]) async throws {
        guard !ids.isEmpty else { return }
        _ = try await APIClient.shared.requestData(
            method: "POST", path: "\(root)/mark-read", body: MarkReadBody(notification_ids: ids)
        )
    }

    static func markAllRead() async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "\(root)/mark-all-read")
    }
}
