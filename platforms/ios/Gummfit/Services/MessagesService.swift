import Foundation

/// Creator↔client inbox (server/app/cappe/routes/messages.py).
final class MessagesService {
    static let shared = MessagesService()
    private init() {}

    func listThreads(siteId: String) async throws -> [CappeThread] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/threads")
    }

    /// Marks the thread read server-side as a side effect of the fetch.
    func getThread(siteId: String, threadId: String) async throws -> CappeThreadDetail {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/threads/\(threadId)")
    }

    /// Starts (or continues, if an open thread with this email exists) a
    /// conversation and sends the first message.
    func startThread(siteId: String, _ body: CappeThreadCreate) async throws -> CappeThreadDetail {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/threads", body: body)
    }

    func reply(siteId: String, threadId: String, body: String) async throws -> CappeMessage {
        try await APIClient.shared.request(
            method: "POST", path: "/sites/\(siteId)/threads/\(threadId)/messages",
            body: CappeMessageCreate(body: body)
        )
    }

    func close(siteId: String, threadId: String) async throws -> CappeThread {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/threads/\(threadId)/close")
    }
}
