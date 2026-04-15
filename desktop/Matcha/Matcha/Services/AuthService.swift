import Foundation

private extension Data {
    mutating func append(_ string: String) {
        if let d = string.data(using: .utf8) { append(d) }
    }
}

class AuthService {
    static let shared = AuthService()
    private let client = APIClient.shared
    private init() {}

    func login(email: String, password: String) async throws -> TokenResponse {
        let body = LoginRequest(email: email, password: password)
        let response: TokenResponse = try await client.request(
            method: "POST",
            path: "/auth/login",
            body: body
        )
        saveTokens(response)
        return response
    }

    func refresh() async throws -> TokenResponse {
        guard let refreshToken = KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) else {
            throw APIError.unauthorized
        }
        let body = RefreshRequest(refresh_token: refreshToken)
        let response: TokenResponse = try await client.request(
            method: "POST",
            path: "/auth/refresh",
            body: body,
            retryOnUnauthorized: false
        )
        saveTokens(response)
        return response
    }

    func logout() async throws {
        if let refreshToken = KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) {
            let body = LogoutRequest(refresh_token: refreshToken)
            _ = try? await client.requestData(method: "POST", path: "/auth/logout", body: body)
        }
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
    }

    func restoreSession() async -> UserInfo? {
        guard KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) != nil else {
            return nil
        }
        do {
            let response = try await refresh()
            return response.user
        } catch {
            return nil
        }
    }

    // MARK: - Profile

    func fetchMe() async throws -> MeResponse {
        try await client.request(method: "GET", path: "/auth/me")
    }

    struct UpdateProfileBody: Encodable {
        let name: String?
        let phone: String?
    }

    func updateProfile(name: String?, phone: String?) async throws {
        _ = try await client.requestData(
            method: "PUT",
            path: "/auth/profile",
            body: UpdateProfileBody(name: name, phone: phone)
        )
    }

    func uploadAvatar(data: Data, filename: String, mimeType: String) async throws -> String {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n")
        body.append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(data)
        body.append("\r\n")
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)/auth/avatar") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (respData, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let msg = String(data: respData, encoding: .utf8) ?? "Upload failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        let decoded = try JSONDecoder().decode(AvatarUploadResponse.self, from: respData)
        return decoded.avatarUrl
    }

    private func saveTokens(_ response: TokenResponse) {
        KeychainHelper.save(key: KeychainHelper.Keys.accessToken, value: response.access_token)
        KeychainHelper.save(key: KeychainHelper.Keys.refreshToken, value: response.refresh_token)
        client.accessToken = response.access_token
    }
}
