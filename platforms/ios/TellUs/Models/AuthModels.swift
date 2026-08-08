import Foundation

/// Mirrors server/app/tellus/models/tellus.py:TellusAccount / client/tellus/src/api/types.ts:12-30.
struct TellusAccount: Codable, Identifiable, Equatable {
    let id: String
    let email: String
    let display_name: String?
    let account_type: AccountType
    let status: String
    let city: String?
    let state: String?
    let leaderboard_opt_in: Bool
    let brand_id: String?
    /// Brand billing state — null for consumer accounts.
    let plan_status: BrandPlanStatus?
    let location_count: Int?
    /// Public review-page slug (brand accounts only) — /tellus/b/{brand_slug}.
    let brand_slug: String?
    /// True when this account's email is in TELLUS_ADMIN_EMAILS.
    let is_admin: Bool

    var isActiveBrand: Bool { account_type == .brand && plan_status == .active }
}

/// NOTE: carries `account:`, not `user:` — differs from Espresso's TokenResponse.
struct TokenResponse: Codable {
    let access_token: String
    let refresh_token: String
    let expires_in: Int
    let account: TellusAccount
}

struct SignupResponse: Codable {
    let verification_required: Bool
    let email: String
    /// Present only when the email is on an RFC-2606 reserved test domain
    /// (auto-verify path, server routes/auth.py:88) — otherwise all nil and
    /// the caller must show the "check your email" screen.
    let access_token: String?
    let refresh_token: String?
    let expires_in: Int?
    let account: TellusAccount?
}

/// Mirrors server TellusSignup (models/tellus.py:27-38). Brand signups
/// require brand_name + location_count (server model_validator enforces).
struct SignupRequest: Encodable {
    let email: String
    let password: String
    let display_name: String?
    let account_type: String
    let brand_name: String?
    let location_count: Int?
    let city: String?
    let state: String?
}

struct LoginRequest: Encodable {
    let email: String
    let password: String
}

struct GoogleSignInRequest: Encodable {
    let id_token: String
}

struct RefreshRequest: Encodable {
    let refresh_token: String
}

struct VerifyRequest: Encodable {
    let token: String
}

struct ResendRequest: Encodable {
    let email: String
}

struct ProfileUpdate: Encodable {
    let display_name: String?
    let leaderboard_opt_in: Bool?
}

/// Consumer's own city update (POST /me/location) — distinct from the
/// brand's LocationUpdateRequest (PATCH /billing/locations), a different
/// field set on a different endpoint.
struct LocationUpdate: Encodable {
    let city: String
    let state: String?
    let zipcode: String?
}

struct PasswordResetConfirm: Encodable {
    let token: String
    let new_password: String
}
