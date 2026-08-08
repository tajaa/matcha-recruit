import Foundation

@MainActor
final class AuthService {
    static let shared = AuthService()
    private let client = APIClient.shared
    /// Coalesced refresh: parallel 401s share ONE task. Without this, two
    /// concurrent callers fire two /auth/refresh POSTs and the server
    /// rotates the refresh token after the first — the loser's stale token
    /// then 401s, logging the user out spuriously.
    private var refreshTask: Task<TokenResponse, Error>?
    private init() {}

    /// POST /auth/login. Server returns 403 for BOTH unverified email and a
    /// suspended account — callers pattern-match `APIError.httpError(403,_)`
    /// and route to the verify-pending screen.
    func login(email: String, password: String) async throws -> TokenResponse {
        let body = LoginRequest(email: email, password: password)
        // retryOnUnauthorized: false — a wrong password is a 401 from THIS
        // endpoint, not a stale access token. Letting the default retry fire
        // would drive AuthService.refresh() with whatever refresh token
        // happens to be in the keychain (possibly a DIFFERENT account's,
        // since restoreSession() never deletes on failure) and replay the
        // login under the wrong bearer.
        let response: TokenResponse = try await client.request(method: "POST", path: "/auth/login", body: body, retryOnUnauthorized: false)
        saveTokens(response)
        return response
    }

    /// POST /auth/signup. If the response carries tokens (reserved-test-
    /// domain auto-verify, server routes/auth.py:88) they're persisted here;
    /// otherwise verification_required is true and the caller shows the
    /// "check your email" screen without a session.
    func signup(_ req: SignupRequest) async throws -> SignupResponse {
        let response: SignupResponse = try await client.request(method: "POST", path: "/auth/signup", body: req, retryOnUnauthorized: false)
        if let access = response.access_token, let refresh = response.refresh_token, let expires = response.expires_in,
           let account = response.account {
            saveTokens(TokenResponse(access_token: access, refresh_token: refresh, expires_in: expires, account: account))
        }
        return response
    }

    /// POST /auth/verify — consumes the emailed token, auto-signs in.
    func verify(token: String) async throws -> TokenResponse {
        let response: TokenResponse = try await client.request(method: "POST", path: "/auth/verify", body: VerifyRequest(token: token), retryOnUnauthorized: false)
        saveTokens(response)
        return response
    }

    /// POST /auth/resend-verification — always 202, never leaks whether the
    /// email exists. Rate-limited 2/min + 6/hr server-side.
    func resendVerification(email: String) async throws {
        try await client.requestVoid(method: "POST", path: "/auth/resend-verification", body: ResendRequest(email: email), retryOnUnauthorized: false)
    }

    /// POST /auth/google. Auto-creates a consumer account on first use, or
    /// links Google to an existing account matched by email — same funnel
    /// as login/verify, tokens persisted here.
    func signInWithGoogle(idToken: String) async throws -> TokenResponse {
        let body = GoogleSignInRequest(id_token: idToken)
        // retryOnUnauthorized: false — a rejected Google token is a 400/401
        // from THIS endpoint, not a stale access token (same reasoning as login).
        let response: TokenResponse = try await client.request(method: "POST", path: "/auth/google", body: body, retryOnUnauthorized: false)
        saveTokens(response)
        return response
    }

    func refresh() async throws -> TokenResponse {
        if let existing = refreshTask {
            return try await existing.value
        }
        let task = Task<TokenResponse, Error> { [weak self] in
            guard let self else { throw APIError.unauthorized }
            defer { self.refreshTask = nil }
            guard let refreshToken = KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) else {
                throw APIError.unauthorized
            }
            let body = RefreshRequest(refresh_token: refreshToken)
            let response: TokenResponse = try await self.client.request(
                method: "POST", path: "/auth/refresh", body: body, retryOnUnauthorized: false
            )
            self.saveTokens(response)
            return response
        }
        refreshTask = task
        return try await task.value
    }

    /// Resolves to nil on any failure (no stored refresh token, or a
    /// definitive rejection) — NEVER deletes keychain on a network failure;
    /// only `_isAuthRejection` paths inside APIClient do that.
    func restoreSession() async -> TellusAccount? {
        guard KeychainHelper.load(key: KeychainHelper.Keys.refreshToken) != nil else { return nil }
        do {
            let response = try await refresh()
            return response.account
        } catch {
            return nil
        }
    }

    func fetchMe() async throws -> TellusAccount {
        try await client.request(method: "GET", path: "/auth/me")
    }

    func updateProfile(_ patch: ProfileUpdate) async throws -> TellusAccount {
        try await client.request(method: "PATCH", path: "/me", body: patch)
    }

    /// Consumer's own city — geocoded server-side, powers the marketplace
    /// city filter.
    func updateLocation(_ update: LocationUpdate) async throws -> TellusAccount {
        try await client.request(method: "POST", path: "/me/location", body: update)
    }

    /// Consumes an admin-minted reset token (no self-serve request endpoint
    /// exists — flagged as a backend gap). Revokes all existing sessions.
    func resetPassword(token: String, newPassword: String) async throws {
        try await client.requestVoid(
            method: "POST", path: "/auth/reset-password",
            body: PasswordResetConfirm(token: token, new_password: newPassword),
            retryOnUnauthorized: false
        )
    }

    /// Server logout is GLOBAL — it advances tokens_valid_after, which kills
    /// every device's session at once. Best-effort POST (never blocks local
    /// logout on a network failure), then clear local state unconditionally.
    func logout() async {
        try? await client.requestVoid(method: "POST", path: "/auth/logout")
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
        client.accessToken = nil
    }

    private func saveTokens(_ response: TokenResponse) {
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
