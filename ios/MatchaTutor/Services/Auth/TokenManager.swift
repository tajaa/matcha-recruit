import Foundation

final class TokenManager {
    static let shared = TokenManager()

    private let keychain = KeychainManager.shared
    private let tokenRefreshThreshold: TimeInterval = 60 // Refresh if expiring within 60 seconds

    private init() {}

    // MARK: - Token State

    var isAuthenticated: Bool {
        keychain.getAccessToken() != nil
    }

    var accessToken: String? {
        keychain.getAccessToken()
    }

    var refreshToken: String? {
        keychain.getRefreshToken()
    }

    var isTokenExpired: Bool {
        guard let expiry = keychain.getTokenExpiry() else { return true }
        return Date() >= expiry
    }

    var shouldRefreshToken: Bool {
        guard let expiry = keychain.getTokenExpiry() else { return true }
        return Date().addingTimeInterval(tokenRefreshThreshold) >= expiry
    }

    // MARK: - Token Management

    func saveTokens(from response: TokenResponse) {
        do {
            try keychain.saveAccessToken(response.accessToken)
            try keychain.saveRefreshToken(response.refreshToken)

            let expiryDate = Date().addingTimeInterval(TimeInterval(response.expiresIn))
            try keychain.saveTokenExpiry(expiryDate)
        } catch {
            print("Failed to save tokens: \(error)")
        }
    }

    func clearTokens() {
        keychain.clearAll()
    }

    // MARK: - Authorization Header

    var authorizationHeader: String? {
        guard let token = accessToken else { return nil }
        return "Bearer \(token)"
    }
}
