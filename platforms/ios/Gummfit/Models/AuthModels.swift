import Foundation

/// Mirrors server/app/cappe/models/auth.py:CappeAccount /
/// client/src/cappe/types.ts:7-14.
struct CappeAccount: Codable, Identifiable, Equatable {
    let id: String
    let email: String
    let name: String?
    let plan: String
    let status: String
    let account_type: AccountType
    let is_platform_admin: Bool
}

/// NOTE: carries `account:`, matching TellUs's TokenResponse shape (not the
/// desktop/Espresso convention of `user:`).
struct CappeTokenResponse: Codable {
    let access_token: String
    let refresh_token: String
    let expires_in: Int
    let account: CappeAccount
}

struct CappeSignupResponse: Codable {
    let verification_required: Bool
    let email: String
    /// Present only when the email is on an RFC-2606 reserved test domain
    /// (auto-verify path, server routes/auth.py:76) — otherwise all nil and
    /// the caller must show the "check your email" screen.
    let access_token: String?
    let refresh_token: String?
    let expires_in: Int?
    let account: CappeAccount?

    /// Single statement of "is this signup response a real session" — all
    /// four fields are independently Optional on the wire, so callers must
    /// not check a subset (a partial response with e.g. `account` +
    /// `access_token` but no `refresh_token` is not a usable session).
    var sessionTokens: CappeTokenResponse? {
        guard let access_token, let refresh_token, let expires_in, let account else { return nil }
        return CappeTokenResponse(access_token: access_token, refresh_token: refresh_token, expires_in: expires_in, account: account)
    }
}

/// Mirrors server CappeSignup (models/auth.py:9-17).
struct CappeSignupRequest: Encodable {
    let email: String
    let password: String
    let name: String?
    let account_type: String
}

struct CappeLoginRequest: Encodable {
    let email: String
    let password: String
}

struct CappeRefreshRequest: Encodable {
    let refresh_token: String
}

struct CappeVerifyRequest: Encodable {
    let token: String
}

struct CappeResendRequest: Encodable {
    let email: String
}
