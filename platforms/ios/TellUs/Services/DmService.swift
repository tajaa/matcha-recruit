import Foundation

/// Unified Comms transport for general business questions and legacy
/// report-linked feedback DMs. The native inbox uses /comms/* so both kinds
/// remain in one list.
final class DmService {
    static let shared = DmService()
    private let client = APIClient.shared
    private init() {}

    func threads(
        brandID: String? = nil,
        kind: DmKind? = nil,
        status: DmStatus? = nil,
        assigned: String? = nil,
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> [DmThread] {
        var items = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ]
        if let brandID { items.append(URLQueryItem(name: "brand_id", value: brandID)) }
        if let kind, kind != .unknown { items.append(URLQueryItem(name: "kind", value: kind.rawValue)) }
        if let status, status != .unknown { items.append(URLQueryItem(name: "status", value: status.rawValue)) }
        if let assigned { items.append(URLQueryItem(name: "assigned", value: assigned)) }
        return try await client.request(method: "GET", path: "/comms/threads" + Self.query(items))
    }

    func messages(threadId: String, after: String? = nil) async throws -> [DmMessage] {
        let suffix = after.map { Self.query([URLQueryItem(name: "after", value: $0)]) } ?? ""
        return try await client.request(method: "GET", path: "/comms/threads/\(threadId)/messages" + suffix)
    }

    func send(threadId: String, body: String, clientMessageId: String = UUID().uuidString) async throws -> DmMessage {
        try await client.request(
            method: "POST", path: "/comms/threads/\(threadId)/messages",
            body: DmSend(body: body, clientMessageId: clientMessageId)
        )
    }

    func start(slug: String, request: CommsStartRequest) async throws -> CommsStartResponse {
        try await client.request(method: "POST", path: "/comms/brands/\(slug)/threads", body: request)
    }

    func inboxBrands() async throws -> [InboxBrand] {
        try await client.request(method: "GET", path: "/comms/inbox-brands")
    }

    func take(threadId: String) async throws -> DmThread {
        try await client.request(method: "POST", path: "/comms/threads/\(threadId)/take")
    }

    func assign(threadId: String, memberID: String?) async throws -> DmThread {
        try await client.request(
            method: "PATCH", path: "/comms/threads/\(threadId)/assignment",
            body: ThreadAssignmentRequest(member_id: memberID)
        )
    }

    func close(threadId: String) async throws -> DmThread {
        try await client.request(method: "POST", path: "/comms/threads/\(threadId)/close")
    }

    /// Brand-side: opens (or reuses) the thread for identified feedback. The
    /// backend requires the opening body in the same request.
    func openFeedbackThread(reportId: String, body: String, clientMessageId: String = UUID().uuidString) async throws -> DmThread {
        try await client.request(
            method: "POST", path: "/feedback/\(reportId)/dm",
            body: DmSend(body: body, clientMessageId: clientMessageId)
        )
    }

    func block(threadId: String) async throws {
        try await client.requestVoid(method: "POST", path: "/comms/threads/\(threadId)/block")
    }

    func unblock(threadId: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/comms/threads/\(threadId)/block")
    }

    func setMessagingEnabled(_ enabled: Bool) async throws {
        try await client.requestVoid(method: "PATCH", path: "/comms/brand/messaging", body: InboxToggleRequest(enabled: enabled))
    }

    func setTeamInboxAccess(memberID: String, enabled: Bool) async throws {
        try await client.requestVoid(method: "PATCH", path: "/comms/team/\(memberID)/inbox", body: InboxToggleRequest(enabled: enabled))
    }

    private static func query(_ items: [URLQueryItem]) -> String {
        var components = URLComponents()
        components.queryItems = items
        return components.percentEncodedQuery.map { "?\($0)" } ?? ""
    }
}
