import Foundation

// MARK: - Models (per-user Gmail, backend: /matcha-work/agent/email/*)

struct EmailStatus: Decodable {
    let connected: Bool
    let email: String?
    /// How many messages one card snapshot takes (server `SNAPSHOT_MAX_EMAILS`).
    var snapshotMaxEmails: Int? = nil

    enum CodingKeys: String, CodingKey {
        case connected, email
        case snapshotMaxEmails = "snapshot_max_emails"
    }
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
    /// Gmail's own one-line preview.
    var snippet: String? = nil
    /// The HTML part, for the sandboxed reader. Only a single-message fetch
    /// carries it — the unread list leaves it out to stay light.
    var bodyHtml: String? = nil
    var isUnread: Bool? = nil

    // `from` is a Swift keyword — map it to fromAddress.
    enum CodingKeys: String, CodingKey {
        case id, subject, date, body, attachments, snippet
        case fromAddress = "from"
        case threadId = "thread_id"
        case messageIdHeader = "message_id_header"
        case bodyHtml = "body_html"
        case isUnread = "is_unread"
    }
}

enum EmailMailbox: String, CaseIterable {
    case unread, read, all
    var title: String {
        switch self {
        case .unread: return "Unread"
        case .read: return "Read"
        case .all: return "All mail"
        }
    }
}

/// A Gmail draft in the Drafts list (no body).
struct EmailDraftSummary: Decodable, Identifiable, Equatable {
    let id: String
    var to: String
    var subject: String
    var snippet: String
    var updatedMs: Double?

    enum CodingKeys: String, CodingKey {
        case id, to, subject, snippet
        case updatedMs = "updated_ms"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        to = (try? c.decodeIfPresent(String.self, forKey: .to)) ?? ""
        subject = (try? c.decodeIfPresent(String.self, forKey: .subject)) ?? ""
        snippet = (try? c.decodeIfPresent(String.self, forKey: .snippet)) ?? ""
        updatedMs = try? c.decodeIfPresent(Double.self, forKey: .updatedMs)
    }

    var updated: Date? { updatedMs.map { Date(timeIntervalSince1970: $0 / 1000) } }
}

/// One draft, to edit and send.
struct EmailDraft: Decodable, Equatable {
    let id: String
    var to: String
    var subject: String
    var body: String
    /// Who else it goes to: kept as they are when it's saved here.
    var cc: String
    var bcc: String
    var threadId: String?
    /// The draft's message in Gmail, for opening it there.
    var messageId: String?
    /// False when saving it here would lose an attachment or its formatting:
    /// it's read, sent and deleted here, and edited in Gmail.
    var editable: Bool
    var hasAttachments: Bool
    var formatted: Bool

    enum CodingKeys: String, CodingKey {
        case id, to, subject, body, cc, bcc, editable, formatted
        case threadId = "thread_id"
        case messageId = "message_id"
        case hasAttachments = "has_attachments"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        to = (try? c.decodeIfPresent(String.self, forKey: .to)) ?? ""
        subject = (try? c.decodeIfPresent(String.self, forKey: .subject)) ?? ""
        body = (try? c.decodeIfPresent(String.self, forKey: .body)) ?? ""
        cc = (try? c.decodeIfPresent(String.self, forKey: .cc)) ?? ""
        bcc = (try? c.decodeIfPresent(String.self, forKey: .bcc)) ?? ""
        threadId = try? c.decodeIfPresent(String.self, forKey: .threadId)
        messageId = try? c.decodeIfPresent(String.self, forKey: .messageId)
        editable = (try? c.decodeIfPresent(Bool.self, forKey: .editable)) ?? true
        hasAttachments = (try? c.decodeIfPresent(Bool.self, forKey: .hasAttachments)) ?? false
        formatted = (try? c.decodeIfPresent(Bool.self, forKey: .formatted)) ?? false
    }
}

struct EmailDraftList: Decodable {
    let drafts: [EmailDraftSummary]
    var nextPageToken: String? = nil

    enum CodingKeys: String, CodingKey {
        case drafts
        case nextPageToken = "next_page_token"
    }
}

struct EmailFetchResponse: Decodable {
    let emails: [EmailMessage]
    var nextPageToken: String? = nil
    enum CodingKeys: String, CodingKey {
        case emails
        case nextPageToken = "next_page_token"
    }
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

    /// Fetches the next 25 messages from the selected mailbox without marking them read.
    func fetch(mailbox: EmailMailbox = .unread, pageToken: String? = nil) async throws -> EmailFetchResponse {
        struct Body: Encodable {
            let mailbox: String
            let page_token: String?
        }
        return try await client.request(method: "POST", path: "\(basePath)/fetch",
                                        body: Body(mailbox: mailbox.rawValue, page_token: pageToken))
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

    // MARK: Drafts

    /// A page of drafts, newest first; pass the last page's token for the next.
    func drafts(pageToken: String? = nil) async throws -> EmailDraftList {
        let query = pageToken.map { "?page_token=\(Self.pathId($0))" } ?? ""
        return try await client.request(method: "GET", path: "\(basePath)/drafts\(query)")
    }

    func draft(id: String) async throws -> EmailDraft {
        try await client.request(method: "GET", path: "\(basePath)/drafts/\(Self.pathId(id))")
    }

    func saveDraft(id: String, to: String, subject: String, body: String) async throws -> EmailDraft {
        struct Body: Encodable { let to: String; let subject: String; let body: String }
        return try await client.request(method: "PUT", path: "\(basePath)/drafts/\(Self.pathId(id))",
                                        body: Body(to: to, subject: subject, body: body))
    }

    func sendDraft(id: String) async throws {
        let _: EmailSendResponse = try await client.request(method: "POST", path: "\(basePath)/drafts/\(Self.pathId(id))/send")
    }

    func deleteDraft(id: String) async throws {
        let _: [String: Bool] = try await client.request(method: "DELETE", path: "\(basePath)/drafts/\(Self.pathId(id))")
    }

    /// Gmail ids are url-safe already (letters, digits, `-`, `_`); anything
    /// else is escaped, so it can never reach a different path.
    nonisolated static func pathId(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-_"))) ?? ""
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
