import Foundation

@MainActor
final class AuthService {
    static let shared = AuthService()
    private let client = APIClient.shared
    /// Coalesced refresh: parallel 401s share ONE task. Without this, two
    /// concurrent callers fire two /auth/refresh POSTs and the server
    /// rotates the refresh token after the first — the loser's stale token
    /// then 401s, logging the user out spuriously.
    private var refreshTask: Task<CappeTokenResponse, Error>?
    private init() {}

    /// POST /auth/login. Server returns 401 for wrong email/password, 403
    /// "Account is not active" for a suspended account, 403 "Please confirm
    /// your email…" for an unverified one (server/app/cappe/routes/auth.py:
    /// 210-229) — callers pattern-match on the 403 detail text to route to
    /// the verify-pending screen.
    func login(email: String, password: String) async throws -> CappeTokenResponse {
        let body = CappeLoginRequest(email: email, password: password)
        // retryOnUnauthorized: false — a wrong password is a 401 from THIS
        // endpoint, not a stale access token. Letting the default retry fire
        // would drive AuthService.refresh() with whatever refresh token
        // happens to be in the keychain (possibly a DIFFERENT account's,
        // since restoreSession() never deletes on failure) and replay the
        // login under the wrong bearer.
        let response: CappeTokenResponse = try await client.request(method: "POST", path: "/auth/login", body: body, retryOnUnauthorized: false)
        saveTokens(response)
        return response
    }

    /// POST /auth/signup. If the response carries tokens (reserved-test-
    /// domain auto-verify, server routes/auth.py:76) they're persisted here;
    /// otherwise verification_required is true and the caller shows the
    /// "check your email" screen without a session.
    func signup(_ req: CappeSignupRequest) async throws -> CappeSignupResponse {
        let response: CappeSignupResponse = try await client.request(method: "POST", path: "/auth/signup", body: req, retryOnUnauthorized: false)
        if let tokens = response.sessionTokens {
            saveTokens(tokens)
        }
        return response
    }

    /// POST /auth/verify — consumes the emailed token, auto-signs in.
    func verify(token: String) async throws -> CappeTokenResponse {
        let response: CappeTokenResponse = try await client.request(method: "POST", path: "/auth/verify", body: CappeVerifyRequest(token: token), retryOnUnauthorized: false)
        saveTokens(response)
        return response
    }

    /// POST /auth/resend-verification — always 202, never leaks whether the
    /// email exists. Rate-limited 2/min + 6/hr server-side.
    func resendVerification(email: String) async throws {
        try await client.requestVoid(method: "POST", path: "/auth/resend-verification", body: CappeResendRequest(email: email), retryOnUnauthorized: false)
    }

    func refresh() async throws -> CappeTokenResponse {
        if let existing = refreshTask {
            return try await existing.value
        }
        let task = Task<CappeTokenResponse, Error> { [weak self] in
            guard let self else { throw APIError.unauthorized }
            defer { self.refreshTask = nil }
            guard let refreshToken = KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) else {
                throw APIError.unauthorized
            }
            let body = CappeRefreshRequest(refresh_token: refreshToken)
            let response: CappeTokenResponse = try await self.client.request(
                method: "POST", path: "/auth/refresh", body: body, retryOnUnauthorized: false
            )
            self.saveTokens(response)
            return response
        }
        refreshTask = task
        return try await task.value
    }

    /// Refreshes a token that will expire during a long-running stream. A
    /// malformed JWT is ignored; the stream's own HTTP response remains the
    /// authoritative failure in that case.
    func ensureFreshToken(minTTL: TimeInterval) async throws {
        guard let token = client.accessToken else { return }
        let pieces = token.split(separator: ".")
        guard pieces.count >= 2 else { return }

        var encodedPayload = String(pieces[1])
        encodedPayload += String(repeating: "=", count: (4 - encodedPayload.count % 4) % 4)
        encodedPayload = encodedPayload.replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        guard let payloadData = Data(base64Encoded: encodedPayload),
              let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any],
              let exp = payload["exp"] as? NSNumber else { return }

        if exp.doubleValue - Date().timeIntervalSince1970 < minTTL {
            _ = try await refresh()
        }
    }

    /// Resolves to nil on any failure (no stored refresh token, or a
    /// definitive rejection) — NEVER deletes keychain on a network failure;
    /// only `_isAuthRejection` paths inside APIClient do that.
    func restoreSession() async -> CappeAccount? {
        guard KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) != nil else { return nil }
        do {
            let response = try await refresh()
            return response.account
        } catch {
            return nil
        }
    }

    func fetchMe() async throws -> CappeAccount {
        try await client.request(method: "GET", path: "/auth/me")
    }

    /// Clears the keychain + in-memory bearer unconditionally — the local
    /// half of a logout, and the ONLY place either keychain key is deleted.
    /// Used both for a user-initiated logout and for a DEFINITIVE refresh
    /// rejection (AppState.didLogout's `_isAuthRejection` branch) — a dead
    /// refresh token must never survive to the next cold launch.
    func clearLocalSession() {
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
        client.accessToken = nil
    }

    /// Server logout is GLOBAL — it advances tokens_valid_after, which kills
    /// every device's session at once. Clears local state SYNCHRONOUSLY
    /// (both this and a subsequent re-login run on @MainActor, so there is
    /// no window for the two to interleave), then fires the server POST
    /// best-effort in the background using the bearer captured BEFORE
    /// clearing — routed around APIClient so it can't observe or touch
    /// whatever session a fast re-login has since established.
    func logout() {
        let token = client.accessToken
        clearLocalSession()
        guard let token else { return }
        let baseURL = client.baseURL
        Task.detached(priority: .utility) {
            guard let url = URL(string: baseURL + "/auth/logout") else { return }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            _ = try? await URLSession.shared.data(for: request)
        }
    }

    private func saveTokens(_ response: CappeTokenResponse) {
        let accessOK = KeychainHelper.save(key: KeychainHelper.Keys.accessToken, value: response.access_token)
        let refreshOK = KeychainHelper.save(key: KeychainHelper.Keys.refreshToken, value: response.refresh_token)
        if !accessOK || !refreshOK {
            // The in-memory token below keeps THIS session working, but a
            // keychain write failed — the next cold launch will find nothing
            // and log the user out. Surface it rather than failing silently.
            NSLog("[Auth] token keychain persist failed (access=\(accessOK) refresh=\(refreshOK)); session will not survive relaunch")
        }
        client.accessToken = response.access_token
    }
}
