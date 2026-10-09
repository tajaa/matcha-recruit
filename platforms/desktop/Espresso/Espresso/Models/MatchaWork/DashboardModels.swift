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

// Labels only: which rows a person gets, which are locked and where the
// picker starts come from the server (`entitlements.workspace.chat_models`).
// Values must be in the server's SUPPORTED_MODELS (matcha_work_ai/_models.py)
// or the override silently runs the plan model. Pro-preview retired from
// matcha-work (2026-07-31). Flash Lite used to send "gemini-3.7-flash-lite",
// which the server never served — it ran Flash; the server now aliases that
// id for builds that still send it. @AppStorage("mw-model") stores the `id`,
// not the value, so existing picks carry over.
let mwModelOptions: [MWModelOption] = [
    MWModelOption(id: "flash-lite", label: "Flash Lite 3.5", value: "gemini-3.5-flash-lite"),
    MWModelOption(id: "flash", label: "Flash 3.7", value: "gemini-3.7-flash"),
    MWModelOption(id: "claude-haiku", label: "Claude Haiku 5.5", value: "claude-haiku-5-5"),
    MWModelOption(id: "claude-sonnet", label: "Claude Sonnet 5.5", value: "claude-sonnet-5-5"),
]

/// The chat model picker for one person. Which rows, which are locked and
/// where it starts are the server's rule (`matcha_work_ai._models.
/// picker_models`, sent as `workspace.chat_models` / `default_chat_model`);
/// this only renders it.
struct MWModelPicker {
    /// Until entitlements load: the Gemini rows every plan has. A Claude row
    /// that appears then vanishes is worse than one that appears late.
    static let unknownRows = [
        MWChatModelRow(id: "gemini-3.5-flash-lite", locked: false),
        MWChatModelRow(id: "gemini-3.7-flash", locked: false),
    ]

    let rows: [MWChatModelRow]
    let defaultModel: String

    init(workspace: MWWorkspaceFlags?) {
        rows = workspace?.chatModels ?? Self.unknownRows
        defaultModel = workspace?.defaultChatModel ?? "gemini-3.7-flash"
    }

    /// The menu rows, in the app's order. Locked rows stay (with a lock and
    /// the paywall) so the upgrade is visible.
    var options: [MWModelOption] {
        let offered = Set(rows.map(\.id))
        return mwModelOptions.filter { offered.contains($0.value) }
    }

    func isLocked(_ option: MWModelOption) -> Bool {
        rows.first { $0.id == option.value }?.locked ?? false
    }

    /// The row a stored `mw-model` id actually runs on: the pick when it is
    /// offered and unlocked, else the server's default. The menu label and
    /// its checkmark both read this, so they name the model the turn runs.
    func option(for id: String) -> MWModelOption? {
        let options = self.options
        if let picked = options.first(where: { $0.id == id }), !isLocked(picked) {
            return picked
        }
        return options.first { $0.value == defaultModel }
    }

    /// The model value to send for a stored pick, or nil (the server's
    /// default) when that row is not offered or is locked.
    func value(for id: String) -> String? {
        guard let option = options.first(where: { $0.id == id }), !isLocked(option) else { return nil }
        return option.value
    }
}
