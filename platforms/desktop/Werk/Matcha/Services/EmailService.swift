import Foundation

// MARK: - Models (per-user Gmail, backend: /matcha-work/agent/email/*)

struct EmailStatus: Decodable {
    let connected: Bool
    let email: String?
}

struct EmailConnectResponse: Decodable {
    let authUrl: String
    enum CodingKeys: String, CodingKey { case authUrl = "auth_url" }
}

struct EmailMessage: Decodable, Identifiable, Equatable {
    let id: String
    let subject: String
    let fromAddress: String
    let date: String
    let body: String

    // `from` is a Swift keyword — map it to fromAddress.
    enum CodingKeys: String, CodingKey {
        case id, subject, date, body
        case fromAddress = "from"
    }
}

struct EmailFetchResponse: Decodable {
    let emails: [EmailMessage]
}

private struct EmailActionResponse: Decodable {
    let status: String?
}

// MARK: - Service

/// Thin wrapper over `APIClient` for the existing per-user Gmail backend.
/// Read-only MVP: connect / status / fetch unread / disconnect. The backend
/// also exposes draft + send (deferred — see plan).
final class EmailService {
    static let shared = EmailService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work/agent/email"

    private init() {}

    func status() async throws -> EmailStatus {
        try await client.request(method: "GET", path: "\(basePath)/status")
    }

    /// Starts Google OAuth; returns the consent URL to open in a browser.
    func connect() async throws -> EmailConnectResponse {
        try await client.request(method: "POST", path: "\(basePath)/connect")
    }

    /// Fetches up to 25 unread messages for the connected account.
    func fetch() async throws -> EmailFetchResponse {
        try await client.request(method: "POST", path: "\(basePath)/fetch")
    }

    func disconnect() async throws {
        let _: EmailActionResponse = try await client.request(method: "DELETE", path: "\(basePath)/disconnect")
    }
}
