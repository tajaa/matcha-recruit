import Foundation

struct LoginRequest: Codable {
    let email: String
    let password: String
}

struct RefreshRequest: Codable {
    let refresh_token: String
}

struct LogoutRequest: Codable {
    let refresh_token: String
}

struct TokenResponse: Codable {
    let access_token: String
    let refresh_token: String
    let expires_in: Int
    let user: UserInfo
}

struct UserInfo: Codable {
    let id: String
    let email: String
    let name: String?
    let role: String
    var avatarUrl: String?
    var phone: String?

    enum CodingKeys: String, CodingKey {
        case id, email, name, role, phone
        case avatarUrl = "avatar_url"
    }
}

/// Flexible decoder for GET /auth/me — only pulls the fields we care about for
/// profile editing. The server returns heterogeneous shapes based on role
/// (admin / client / candidate / individual); unknown keys are ignored.
struct MeResponse: Codable {
    struct User: Codable {
        let id: String
        let email: String
        let role: String
        let avatarUrl: String?
        enum CodingKeys: String, CodingKey {
            case id, email, role
            case avatarUrl = "avatar_url"
        }
    }
    struct Profile: Codable {
        let name: String?
        let phone: String?
    }
    let user: User
    let profile: Profile?
}

struct AvatarUploadResponse: Codable {
    let avatarUrl: String
    enum CodingKeys: String, CodingKey {
        case avatarUrl = "avatar_url"
    }
}
