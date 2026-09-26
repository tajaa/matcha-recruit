import Foundation
import UIKit

private struct LoginBody: Encodable {
    let email: String
    let password: String
    let client = "ios_schedule"
    let device_name: String
}

private struct RefreshBody: Encodable {
    let refresh_token: String
}

enum SessionError: LocalizedError {
    case noStoredSession
    case storageFailed
    case employeeOnly
    case invalidCredentials(String)

    var errorDescription: String? {
        switch self {
        case .noStoredSession: "Please sign in again."
        case .storageFailed: "Could not save the session securely. Please try again."
        case .employeeOnly: "This app is for employees. Use Matcha on the web for other roles."
        case .invalidCredentials(let message): message
        }
    }
}

@MainActor
final class AuthService {
    static let shared = AuthService()
    private let refreshGate = RefreshGate()
    private init() {}

    var hasStoredSession: Bool {
        KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) != nil
    }

    func login(email: String, password: String) async throws -> AuthUser {
        let response: TokenResponse
        do {
            response = try await APIClient.shared.request(
                method: "POST", path: "/auth/login",
                body: LoginBody(email: email, password: password, device_name: UIDevice.current.name),
                retryOnUnauthorized: false, credentialExchange: true
            )
        } catch APIError.httpError(401, let message) {
            // The server's own wording ("Invalid email or password"), not the
            // session-expired copy.
            throw SessionError.invalidCredentials(message)
        }
        guard response.user.role == "employee" else { throw SessionError.employeeOnly }
        try store(response)
        return response.user
    }

    func refresh() async throws -> TokenResponse {
        try await refreshGate.run {
            guard let stored = KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) else {
                throw APIError.unauthorized
            }
            let response: TokenResponse = try await APIClient.shared.request(
                method: "POST", path: "/auth/refresh",
                body: RefreshBody(refresh_token: stored), retryOnUnauthorized: false
            )
            guard response.user.role == "employee" else { throw SessionError.employeeOnly }
            try self.store(response)
            return response
        }
    }

    /// Sign out always succeeds locally. On a shared or handed-off phone with
    /// no signal the employee must still be able to leave; the server-side
    /// revoke is queued and flushed on the next launch (`flushPendingRevoke`).
    /// Any non-network failure means the session is already dead server-side.
    func logout() async {
        guard let token = KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) else {
            clearLocalSession()
            return
        }
        do {
            _ = try await APIClient.shared.requestData(
                method: "POST", path: "/auth/mobile/logout",
                body: RefreshBody(refresh_token: token), retryOnUnauthorized: false
            )
        } catch {
            if Self.isNetworkFailure(error) {
                KeychainHelper.save(key: KeychainHelper.Keys.pendingRevoke, value: token)
            }
        }
        clearLocalSession()
    }

    /// Best-effort delivery of a revoke that could not be sent at sign-out.
    func flushPendingRevoke() async {
        guard let token = KeychainHelper.load(key: KeychainHelper.Keys.pendingRevoke) else { return }
        do {
            _ = try await APIClient.shared.requestData(
                method: "POST", path: "/auth/mobile/logout",
                body: RefreshBody(refresh_token: token), retryOnUnauthorized: false
            )
        } catch {
            if Self.isNetworkFailure(error) { return }  // keep it for next time
        }
        KeychainHelper.delete(key: KeychainHelper.Keys.pendingRevoke)
    }

    nonisolated static func isNetworkFailure(_ error: Error) -> Bool {
        if case APIError.networkUnavailable = error { return true }
        if case APIError.serviceUnavailable = error { return true }
        return error is URLError
    }

    func clearLocalSession() {
        APIClient.shared.accessToken = nil
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
    }

    private func store(_ response: TokenResponse) throws {
        guard KeychainHelper.save(key: KeychainHelper.Keys.refreshToken, value: response.refresh_token),
              KeychainHelper.save(key: KeychainHelper.Keys.accessToken, value: response.access_token) else {
            throw SessionError.storageFailed
        }
        APIClient.shared.accessToken = response.access_token
    }
}

@MainActor
final class RefreshGate {
    private var inFlight: Task<TokenResponse, Error>?

    func run(_ operation: @escaping @MainActor () async throws -> TokenResponse) async throws -> TokenResponse {
        if let inFlight { return try await inFlight.value }
        let task = Task { try await operation() }
        inFlight = task
        defer { inFlight = nil }
        return try await task.value
    }
}
