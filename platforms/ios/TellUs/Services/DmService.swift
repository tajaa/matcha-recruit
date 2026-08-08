import Foundation

/// Direct messages between a consumer and a brand, anchored to a feedback
/// report (routes/dms.py). Shared by both roles — MessagesListView /
/// DmThreadView render differently per role but call the same service.
final class DmService {
    static let shared = DmService()
    private let client = APIClient.shared
    private init() {}

    func threads() async throws -> [DmThread] {
        try await client.request(method: "GET", path: "/dm/threads")
    }

    func messages(threadId: String) async throws -> [DmMessage] {
        try await client.request(method: "GET", path: "/dm/threads/\(threadId)/messages")
    }

    func send(threadId: String, body: String) async throws -> DmMessage {
        try await client.request(method: "POST", path: "/dm/threads/\(threadId)/messages", body: DmSend(body: body))
    }

    /// Brand-side: opens (or returns the existing) thread for an identified
    /// report. Gated server-side the same way web is — identified feedback only.
    func openFromReport(reportId: String) async throws -> DmThread {
        try await client.request(method: "POST", path: "/feedback/\(reportId)/dm")
    }

    func block(threadId: String) async throws {
        try await client.requestVoid(method: "POST", path: "/dm/threads/\(threadId)/block")
    }

    func unblock(threadId: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/dm/threads/\(threadId)/block")
    }
}
