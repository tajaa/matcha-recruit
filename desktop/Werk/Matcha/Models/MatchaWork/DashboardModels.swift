import Foundation

// MARK: - Notifications

struct MWAppNotification: Codable, Identifiable {
    let id: String
    let type: String
    let title: String
    let body: String?
    let link: String?
    let isRead: Bool
    let createdAt: String
    /// Target IDs for navigation (project_id / task_id / thread_id / channel_id).
    /// Most notifications carry the real target here rather than in `link`.
    let metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case id, type, title, body, link, metadata
        case isRead = "is_read"
        case createdAt = "created_at"
    }
}

// MARK: - Online Users (Presence)

struct MWOnlineUser: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let avatarUrl: String?
    let lastActive: String?

    enum CodingKeys: String, CodingKey {
        case id, email, name
        case avatarUrl = "avatar_url"
        case lastActive = "last_active"
    }
}

// MARK: - Review Requests

struct MWSendReviewRequestsRequest: Codable {
    let recipientEmails: [String]
    let customMessage: String?

    enum CodingKeys: String, CodingKey {
        case recipientEmails = "recipient_emails"
        case customMessage = "custom_message"
    }
}

struct MWSendReviewRequestsResponse: Codable {
    let sentCount: Int
    let failedCount: Int
    let failedEmails: [String]?

    enum CodingKeys: String, CodingKey {
        case sentCount = "sent_count"
        case failedCount = "failed_count"
        case failedEmails = "failed_emails"
    }
}

// MARK: - Email Agent

struct MWAgentEmail: Codable, Identifiable {
    let id: String
    let subject: String?
    let from: String?
    let date: String?
    let body: String?
}

struct MWAgentEmailStatus: Codable {
    let connected: Bool
    let email: String?
    let lastSync: String?

    enum CodingKeys: String, CodingKey {
        case connected, email
        case lastSync = "last_sync"
    }
}

// MARK: - Model Options

struct MWModelOption: Identifiable {
    let id: String
    let label: String
    let value: String
}

let mwModelOptions: [MWModelOption] = [
    MWModelOption(id: "flash-lite", label: "Flash Lite 3.1", value: "gemini-2.0-flash-lite"),
    MWModelOption(id: "flash", label: "Flash 3.5", value: "gemini-3.5-flash"),
    MWModelOption(id: "pro", label: "Pro 3.1", value: "gemini-2.5-pro-preview-05-06"),
]
