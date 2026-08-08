import Foundation

final class NotificationsService {
    static let shared = NotificationsService()
    private let client = APIClient.shared
    private init() {}

    func list(unreadOnly: Bool = false, limit: Int = 30) async throws -> [TellusNotification] {
        var components = URLComponents()
        components.queryItems = [
            URLQueryItem(name: "unread_only", value: unreadOnly ? "true" : "false"),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        let query = components.percentEncodedQuery.map { "?" + $0 } ?? ""
        return try await client.request(method: "GET", path: "/notifications" + query)
    }

    /// POST /notifications/read[?notification_id={id}] — QUERY param, not
    /// body (server rewards.py:104-107). id nil marks ALL notifications read.
    func markRead(id: String? = nil) async throws {
        var path = "/notifications/read"
        if let id { path += "?notification_id=\(id)" }
        try await client.requestVoid(method: "POST", path: path)
    }
}
