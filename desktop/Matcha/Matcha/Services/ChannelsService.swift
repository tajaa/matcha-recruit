import Foundation

private extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) { append(data) }
    }
}

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

    // MARK: - Attachment upload

    private struct UploadResponse: Codable {
        let attachments: [ChannelAttachment]
    }

    func uploadAttachments(
        channelId: String,
        files: [(data: Data, filename: String, mimeType: String)]
    ) async throws -> [ChannelAttachment] {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        for file in files {
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(file.filename)\"\r\n")
            body.append("Content-Type: \(file.mimeType)\r\n\r\n")
            body.append(file.data)
            body.append("\r\n")
        }
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/\(channelId)/upload") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            let detail = String(data: data, encoding: .utf8) ?? "Upload failed"
            throw APIError.httpError(code, detail)
        }
        let decoded = try JSONDecoder().decode(UploadResponse.self, from: data)
        return decoded.attachments
    }
}
