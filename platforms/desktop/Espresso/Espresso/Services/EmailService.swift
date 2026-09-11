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

/// Listed by name only — attachment bytes stay in Gmail.
struct EmailAttachment: Decodable, Equatable, Hashable {
    let filename: String
    let mimeType: String
    let attachmentId: String

    enum CodingKeys: String, CodingKey {
        case filename
        case mimeType = "mime_type"
        case attachmentId = "attachment_id"
    }
}

struct EmailMessage: Decodable, Identifiable, Equatable {
    let id: String
    let subject: String
    let fromAddress: String
    let date: String
    let body: String
    /// Gmail's conversation id — keeps a reply in its thread.
    let threadId: String?
    /// The RFC 5322 `Message-ID` header — becomes a reply's `In-Reply-To`.
    let messageIdHeader: String?
    let attachments: [EmailAttachment]?

    // `from` is a Swift keyword — map it to fromAddress.
    enum CodingKeys: String, CodingKey {
        case id, subject, date, body, attachments
        case fromAddress = "from"
        case threadId = "thread_id"
        case messageIdHeader = "message_id_header"
    }
}

struct EmailFetchResponse: Decodable {
    let emails: [EmailMessage]
}

struct EmailSummaryResponse: Decodable {
    let summary: String
}

/// An AI reply the server already saved as a Gmail draft in the thread.
struct EmailDraftResponse: Decodable, Identifiable {
    let draftId: String?
    let to: String
    let subject: String
    let body: String
    let threadId: String?
    let inReplyTo: String?

    var id: String { draftId ?? "\(to)|\(subject)|\(body.count)" }

    enum CodingKeys: String, CodingKey {
        case to, subject, body
        case draftId = "draft_id"
        case threadId = "thread_id"
        case inReplyTo = "in_reply_to"
    }
}

struct EmailSendResponse: Decodable {
    let messageId: String?
    enum CodingKeys: String, CodingKey { case messageId = "message_id" }
}

/// In-app triage only — nothing is labelled or archived in Gmail.
enum EmailTriageBucket: String, Decodable, CaseIterable {
    case needsReply = "needs_reply"
    case action
    case fyi
    case newsletter

    var label: String {
        switch self {
        case .needsReply: return "Needs reply"
        case .action: return "Action"
        case .fyi: return "FYI"
        case .newsletter: return "Newsletters"
        }
    }

    var icon: String {
        switch self {
        case .needsReply: return "arrowshape.turn.up.left"
        case .action: return "checklist"
        case .fyi: return "info.circle"
        case .newsletter: return "newspaper"
        }
    }
}

struct EmailTriageEntry: Decodable, Equatable {
    let emailId: String
    let bucket: EmailTriageBucket
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case bucket, reason
        case emailId = "email_id"
    }
}

struct EmailTriageResponse: Decodable {
    let buckets: [EmailTriageEntry]
}

private struct EmailActionResponse: Decodable {
    let status: String?
}

private struct EmailIdBody: Encodable {
    let emailId: String
    enum CodingKeys: String, CodingKey { case emailId = "email_id" }
}

private struct EmailDraftBody: Encodable {
    let emailId: String
    let instructions: String?
    enum CodingKeys: String, CodingKey {
        case instructions
        case emailId = "email_id"
    }
}

private struct EmailSendBody: Encodable {
    let to: String
    let subject: String
    let body: String
    let threadId: String?
    let inReplyTo: String?
    let draftId: String?
    enum CodingKeys: String, CodingKey {
        case to, subject, body
        case threadId = "thread_id"
        case inReplyTo = "in_reply_to"
        case draftId = "draft_id"
    }
}

private struct EmailTriageBody: Encodable {
    let emailIds: [String]
    enum CodingKeys: String, CodingKey { case emailIds = "email_ids" }
}

// MARK: - Service

/// Thin wrapper over `APIClient` for the per-user Gmail backend: connect /
/// status / fetch unread / read one / disconnect, plus the Flash Lite AI
/// actions (summarize, draft reply, triage — all Lite+ `email_ai`) and send.
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

    /// One message by Gmail id — for a message no longer in the unread list.
    func message(id: String) async throws -> EmailMessage {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
        let encoded = id.addingPercentEncoding(withAllowedCharacters: allowed) ?? id
        return try await client.request(method: "GET", path: "\(basePath)/messages/\(encoded)")
    }

    func summarize(emailId: String) async throws -> EmailSummaryResponse {
        try await client.request(method: "POST", path: "\(basePath)/summarize", body: EmailIdBody(emailId: emailId))
    }

    /// Drafts a reply AND saves it as a Gmail draft in the original thread.
    func draftReply(emailId: String, instructions: String?) async throws -> EmailDraftResponse {
        let trimmed = instructions?.trimmingCharacters(in: .whitespacesAndNewlines)
        let body = EmailDraftBody(emailId: emailId, instructions: (trimmed?.isEmpty ?? true) ? nil : trimmed)
        return try await client.request(method: "POST", path: "\(basePath)/draft", body: body)
    }

    /// Sends now. Pass the AI draft's id so the server removes the saved
    /// draft once the edited version has gone out.
    @discardableResult
    func send(
        to: String,
        subject: String,
        body: String,
        threadId: String?,
        inReplyTo: String?,
        draftId: String? = nil
    ) async throws -> EmailSendResponse {
        let payload = EmailSendBody(
            to: to, subject: subject, body: body,
            threadId: threadId, inReplyTo: inReplyTo, draftId: draftId
        )
        return try await client.request(method: "POST", path: "\(basePath)/send", body: payload)
    }

    func triage(emailIds: [String]) async throws -> EmailTriageResponse {
        try await client.request(method: "POST", path: "\(basePath)/triage", body: EmailTriageBody(emailIds: emailIds))
    }

    func disconnect() async throws {
        let _: EmailActionResponse = try await client.request(method: "DELETE", path: "\(basePath)/disconnect")
    }
}

// MARK: - Email kanban cards

struct EmailSnapshotFile: Decodable {
    let id: String
    let filename: String
}

struct EmailSnapshotSkipped: Decodable {
    let emailId: String
    let reason: String
    enum CodingKeys: String, CodingKey {
        case reason
        case emailId = "email_id"
    }
}

struct EmailSnapshotResponse: Decodable {
    let files: [EmailSnapshotFile]
    let skipped: [EmailSnapshotSkipped]
}

private struct EmailSnapshotBody: Encodable {
    let emailIds: [String]
    let projectId: String
    let taskId: String
    enum CodingKeys: String, CodingKey {
        case emailIds = "email_ids"
        case projectId = "project_id"
        case taskId = "task_id"
    }
}

extension EmailService {
    /// Server renders each message to `email-<message id>.md` and attaches it to the
    /// task — the corpus an `email` card hands the AutoPR run. Idempotent.
    func snapshot(emailIds: [String], projectId: String, taskId: String) async throws -> EmailSnapshotResponse {
        try await APIClient.shared.request(
            method: "POST",
            path: "/matcha-work/agent/email/snapshot",
            body: EmailSnapshotBody(emailIds: emailIds, projectId: projectId, taskId: taskId)
        )
    }
}
