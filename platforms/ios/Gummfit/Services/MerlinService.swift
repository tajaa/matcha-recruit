import Foundation

final class MerlinService {
    static let shared = MerlinService()
    private init() {}

    func schema() async throws -> CappeEditorSchema {
        try await APIClient.shared.request(method: "GET", path: "/merlin/schema")
    }

    func conversations(siteId: String, pageId: String) async throws -> [CappeMerlinConversation] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/pages/\(pageId)/merlin/conversations")
    }

    func createConversation(siteId: String, pageId: String, title: String?) async throws -> CappeMerlinConversation {
        struct Body: Encodable { let title: String? }
        return try await APIClient.shared.request(
            method: "POST", path: "/sites/\(siteId)/pages/\(pageId)/merlin/conversations",
            body: Body(title: title)
        )
    }

    func conversation(_ id: String) async throws -> CappeMerlinConversationDetail {
        try await APIClient.shared.request(method: "GET", path: "/merlin/conversations/\(id)")
    }

    func renameConversation(_ id: String, title: String) async throws -> CappeMerlinConversation {
        struct Body: Encodable { let title: String }
        return try await APIClient.shared.request(method: "PATCH", path: "/merlin/conversations/\(id)", body: Body(title: title))
    }

    func deleteConversation(_ id: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/merlin/conversations/\(id)")
    }

    func reportResults(messageId: String, _ results: [CappeMerlinOpResult]) async throws {
        try await APIClient.shared.requestVoid(method: "PATCH", path: "/merlin/messages/\(messageId)/results", body: CappeMerlinResultsUpdate(results: results))
    }

    func agent(
        siteId: String,
        _ body: CappeMerlinChatRequest,
        onFrame: @escaping (CappeMerlinFrame) -> Void
    ) async throws {
        try await stream(path: "/sites/\(siteId)/merlin/agent", body: body, onFrame: onFrame)
    }

    func setupAgent(
        siteId: String,
        _ body: CappeMerlinSetupRequest,
        onFrame: @escaping (CappeMerlinFrame) -> Void
    ) async throws {
        try await stream(path: "/sites/\(siteId)/merlin/setup/agent", body: body, onFrame: onFrame)
    }

    func setupConversations(siteId: String) async throws -> [CappeMerlinConversation] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/merlin/setup/conversations")
    }

    func setupConversation(_ id: String) async throws -> CappeMerlinConversationDetail {
        try await APIClient.shared.request(method: "GET", path: "/merlin/setup/conversations/\(id)")
    }

    func executeAction(conversationId: String, actionId: String) async throws -> CappeSetupActionResult {
        try await APIClient.shared.request(method: "POST", path: "/merlin/setup/conversations/\(conversationId)/actions/\(actionId)/execute")
    }

    func dismissAction(conversationId: String, actionId: String) async throws -> CappeMerlinConversationDetail {
        try await APIClient.shared.request(method: "POST", path: "/merlin/setup/conversations/\(conversationId)/actions/\(actionId)/dismiss")
    }

    private func stream(
        path: String,
        body: any Encodable,
        onFrame: @escaping (CappeMerlinFrame) -> Void
    ) async throws {
        var receivedTerminalFrame = false
        try await APIClient.shared.streamSSE(path: path, body: body) { data in
            guard let frame = try? JSONDecoder().decode(CappeMerlinFrame.self, from: data) else {
                return false
            }
            onFrame(frame)
            if case .result = frame { receivedTerminalFrame = true; return true }
            if case .setupResult = frame { receivedTerminalFrame = true; return true }
            return false
        }
        guard receivedTerminalFrame else { throw APIError.noData }
    }
}
