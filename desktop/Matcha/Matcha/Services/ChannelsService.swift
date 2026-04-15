import Foundation

class ChannelsService {
    static let shared = ChannelsService()
    private let client = APIClient.shared
    private let basePath = "/channels"
    private init() {}

    func listChannels() async throws -> [ChannelSummary] {
        try await client.request(method: "GET", path: basePath)
    }

    func getChannel(id: String) async throws -> ChannelDetail {
        try await client.request(method: "GET", path: "\(basePath)/\(id)")
    }

    func getMessages(channelId: String, before: String? = nil, limit: Int = 50) async throws -> [ChannelMessage] {
        var path = "\(basePath)/\(channelId)/messages?limit=\(limit)"
        if let before, !before.isEmpty {
            let encoded = before.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? before
            path += "&before=\(encoded)"
        }
        return try await client.request(method: "GET", path: path)
    }

    struct JoinResponse: Codable { let ok: Bool? }

    func joinChannel(id: String) async throws {
        let _: JoinResponse = try await client.request(method: "POST", path: "\(basePath)/\(id)/join")
    }

    func leaveChannel(id: String) async throws {
        let _: JoinResponse = try await client.request(method: "POST", path: "\(basePath)/\(id)/leave")
    }

    struct CreateRequest: Encodable {
        let name: String
        let description: String?
        let visibility: String
    }

    func createChannel(name: String, description: String?, visibility: String = "public") async throws -> ChannelDetail {
        let body = CreateRequest(name: name, description: description, visibility: visibility)
        return try await client.request(method: "POST", path: basePath, body: body)
    }

    // MARK: - Connections

    func listConnections() async throws -> [UserConnection] {
        try await client.request(method: "GET", path: "\(basePath)/connections")
    }

    func listPendingConnections() async throws -> [UserConnection] {
        try await client.request(method: "GET", path: "\(basePath)/connections/pending")
    }

    func listSentConnections() async throws -> [UserConnection] {
        try await client.request(method: "GET", path: "\(basePath)/connections/sent")
    }

    private struct ConnectionBody: Encodable {
        let userId: String
        enum CodingKeys: String, CodingKey { case userId = "user_id" }
    }

    private struct ConnectionAck: Codable {
        let ok: Bool?
        let status: String?
    }

    func sendConnectionRequest(userId: String) async throws {
        let _: ConnectionAck = try await client.request(
            method: "POST",
            path: "\(basePath)/connections/request",
            body: ConnectionBody(userId: userId)
        )
    }

    func acceptConnection(userId: String) async throws {
        let _: ConnectionAck = try await client.request(
            method: "POST",
            path: "\(basePath)/connections/accept",
            body: ConnectionBody(userId: userId)
        )
    }

    func declineConnection(userId: String) async throws {
        let _: ConnectionAck = try await client.request(
            method: "POST",
            path: "\(basePath)/connections/decline",
            body: ConnectionBody(userId: userId)
        )
    }

    private struct EmptyBody: Encodable {}
}
