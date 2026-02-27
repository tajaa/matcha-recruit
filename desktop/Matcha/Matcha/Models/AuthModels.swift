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
}
