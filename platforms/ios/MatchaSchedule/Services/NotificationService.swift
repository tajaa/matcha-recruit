import Foundation

enum NotificationService {
    private static let root = "/matcha-work/notifications"
    private struct UnreadResponse: Decodable { let count: Int }
    private struct MarkReadBody: Encodable { let notification_ids: [String] }

    /// `typePrefix` narrows the bell to one family (a business admin's bell
    /// also holds their web notifications).
    static func list(typePrefix: String? = nil) async throws -> NotificationsResponse {
        try await APIClient.shared.request(method: "GET", path: "\(root)?limit=50&offset=0\(filter(typePrefix, "&"))")
    }

    static func unreadCount(typePrefix: String? = nil) async throws -> Int {
        let response: UnreadResponse = try await APIClient.shared.request(
            method: "GET", path: "\(root)/unread-count\(filter(typePrefix, "?"))"
        )
        return response.count
    }

    private static func filter(_ typePrefix: String?, _ separator: String) -> String {
        guard let typePrefix else { return "" }
        return "\(separator)type_prefix=\(typePrefix)"
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
