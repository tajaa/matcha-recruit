import Foundation

final class InboxService {
    static let shared = InboxService()
    private init() {}
    private let root = "/inbox"

    func conversations() async throws -> [MWInboxConversation] {
        try await APIClient.shared.request(method: "GET", path: "\(root)/conversations?limit=100&offset=0")
    }

    func conversation(_ id: String) async throws -> MWInboxConversationDetail {
        try await APIClient.shared.request(method: "GET", path: "\(root)/conversations/\(id)?limit=100")
    }

    func unreadCount() async throws -> Int {
        struct Response: Decodable { let count: Int }
        let response: Response = try await APIClient.shared.request(method: "GET", path: "\(root)/unread-count")
        return response.count
    }

    func searchUsers(_ query: String) async throws -> [MWInboxUserSearch] {
        var components = URLComponents()
        components.queryItems = [URLQueryItem(name: "q", value: query)]
        return try await APIClient.shared.request(
            method: "GET", path: "\(root)/search-users?\(components.percentEncodedQuery ?? "")"
        )
    }

    func markRead(_ id: String) async throws {
        _ = try await APIClient.shared.requestData(method: "PUT", path: "\(root)/conversations/\(id)/read")
    }

    func createConversation(with userID: String, message: String) async throws -> MWInboxConversationDetail {
        let ids = try JSONSerialization.data(withJSONObject: [userID])
        return try await multipart(
            path: "\(root)/conversations",
            fields: [("participant_ids", String(decoding: ids, as: UTF8.self)), ("message", message)]
        )
    }

    func sendMessage(_ text: String, in conversationID: String) async throws -> MWInboxMessage {
        try await multipart(path: "\(root)/conversations/\(conversationID)/messages", fields: [("content", text)])
    }

    /// Inbox writes use form data. A 401 can safely be replayed after refresh
    /// because the server rejected that request; connection failures are never
    /// auto-replayed because the server may already have saved the message.
    private func multipart<T: Decodable>(
        path: String, fields: [(String, String)], retryOnUnauthorized: Bool = true
    ) async throws -> T {
        guard let url = URL(string: APIClient.shared.baseURL + path) else { throw APIError.invalidURL }
        let boundary = "MatchaSchedule-\(UUID().uuidString)"
        var payload = Data()
        for (name, value) in fields {
            payload.append("--\(boundary)\r\n")
            payload.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            payload.append("\(value)\r\n")
        }
        payload.append("--\(boundary)--\r\n")

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = APIClient.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = payload

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.noData }
        if http.statusCode == 401 && retryOnUnauthorized {
            _ = try await AuthService.shared.refresh()
            return try await multipart(path: path, fields: fields, retryOnUnauthorized: false)
        }
        if http.statusCode == 401 {
            await MainActor.run { APIClient.shared.onUnauthorized?() }
            throw APIError.unauthorized
        }
        guard (200...299).contains(http.statusCode) else {
            let raw = String(data: data, encoding: .utf8) ?? "Request failed"
            let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw APIError.httpError(http.statusCode, parsed?["detail"] as? String ?? raw)
        }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw APIError.decodingError(error) }
    }
}

private extension Data {
    mutating func append(_ string: String) { append(Data(string.utf8)) }
}
