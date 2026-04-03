import Foundation

class InboxService {
    static let shared = InboxService()
    private let client = APIClient.shared
    private let basePath = "/inbox"
    private init() {}

    func listConversations(limit: Int = 50, offset: Int = 0) async throws -> [MWInboxConversation] {
        try await client.request(method: "GET", path: "\(basePath)/conversations?limit=\(limit)&offset=\(offset)")
    }

    func getConversation(id: String, limit: Int = 50) async throws -> MWInboxConversationDetail {
        try await client.request(method: "GET", path: "\(basePath)/conversations/\(id)?limit=\(limit)")
    }

    func createConversation(participantIds: [String], message: String, title: String? = nil, files: [(data: Data, filename: String, mimeType: String)]? = nil) async throws -> MWInboxConversationDetail {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()

        func appendField(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            body.append("\(value)\r\n")
        }

        let idsJson = try JSONSerialization.data(withJSONObject: participantIds)
        appendField("participant_ids", String(data: idsJson, encoding: .utf8) ?? "[]")
        appendField("message", message)
        if let title { appendField("title", title) }

        if let files {
            for file in files {
                body.append("--\(boundary)\r\n")
                body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(file.filename)\"\r\n")
                body.append("Content-Type: \(file.mimeType)\r\n\r\n")
                body.append(file.data)
                body.append("\r\n")
            }
        }
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/conversations") else {
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
            let msg = String(data: data, encoding: .utf8) ?? "Create failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        return try JSONDecoder().decode(MWInboxConversationDetail.self, from: data)
    }

    func sendMessage(conversationId: String, content: String, files: [(data: Data, filename: String, mimeType: String)]? = nil) async throws -> MWInboxMessage {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()

        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"content\"\r\n\r\n")
        body.append("\(content)\r\n")

        if let files {
            for file in files {
                body.append("--\(boundary)\r\n")
                body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(file.filename)\"\r\n")
                body.append("Content-Type: \(file.mimeType)\r\n\r\n")
                body.append(file.data)
                body.append("\r\n")
            }
        }
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/conversations/\(conversationId)/messages") else {
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
            let msg = String(data: data, encoding: .utf8) ?? "Send failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        return try JSONDecoder().decode(MWInboxMessage.self, from: data)
    }

    func markRead(conversationId: String) async throws {
        _ = try await client.requestData(method: "PUT", path: "\(basePath)/conversations/\(conversationId)/read")
    }

    func toggleMute(conversationId: String) async throws -> Bool {
        struct Resp: Codable { let muted: Bool }
        let resp: Resp = try await client.request(method: "PUT", path: "\(basePath)/conversations/\(conversationId)/mute")
        return resp.muted
    }

    func getUnreadCount() async throws -> Int {
        struct Resp: Codable { let count: Int }
        let resp: Resp = try await client.request(method: "GET", path: "\(basePath)/unread-count")
        return resp.count
    }

    func searchUsers(query: String) async throws -> [MWInboxUserSearch] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        return try await client.request(method: "GET", path: "\(basePath)/search-users?q=\(encoded)")
    }
}

private extension Data {
    mutating func append(_ string: String) {
        if let d = string.data(using: .utf8) { append(d) }
    }
}
