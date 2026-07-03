import Foundation

enum UserRole: String, Codable {
    case admin
    case client
    case candidate
    case employee
    case creator
    case agency
    case gumfitAdmin = "gumfit_admin"
}

struct User: Codable, Identifiable {
    let id: String
    let email: String
    let role: UserRole
    let isActive: Bool
    let createdAt: String
    let lastLogin: String?

    enum CodingKeys: String, CodingKey {
        case id, email, role
        case isActive = "is_active"
        case createdAt = "created_at"
        case lastLogin = "last_login"
    }
}

struct CurrentUser: Codable {
    let id: String
    let email: String
    let role: UserRole
    let betaFeatures: [String: Bool]?
    let interviewPrepTokens: Int?
    let allowedInterviewRoles: [String]?

    enum CodingKeys: String, CodingKey {
        case id, email, role
        case betaFeatures = "beta_features"
        case interviewPrepTokens = "interview_prep_tokens"
        case allowedInterviewRoles = "allowed_interview_roles"
    }
}

struct CurrentUserResponse: Codable {
    let user: CurrentUser
    let profile: AnyCodable?
}

struct TokenResponse: Codable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int
    let user: User

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
        case user
    }
}

struct LoginRequest: Codable {
    let email: String
    let password: String
}

// Helper for dynamic JSON values
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if container.decodeNil() {
            value = NSNull()
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let dict = value as? [String: Any] {
            try container.encode(dict.mapValues { AnyCodable($0) })
        } else if let array = value as? [Any] {
            try container.encode(array.map { AnyCodable($0) })
        } else if let string = value as? String {
            try container.encode(string)
        } else if let int = value as? Int {
            try container.encode(int)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let bool = value as? Bool {
            try container.encode(bool)
        } else if value is NSNull {
            try container.encodeNil()
        }
    }
}
