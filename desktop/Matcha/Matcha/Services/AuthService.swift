import Foundation

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

    private func saveTokens(_ response: TokenResponse) {
        KeychainHelper.save(key: KeychainHelper.Keys.accessToken, value: response.access_token)
        KeychainHelper.save(key: KeychainHelper.Keys.refreshToken, value: response.refresh_token)
    }
}
