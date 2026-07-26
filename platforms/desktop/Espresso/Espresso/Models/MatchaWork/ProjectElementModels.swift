import Foundation

// MARK: - Project Element

struct MWProjectElement: Identifiable, Codable, Equatable {
    let id: String
    let projectId: String
    var name: String
    var kind: String?
    var description: String?
    var assignedTo: String?
    var assignedName: String?
    var order: Int
    /// Git repo-binding: glob patterns (e.g. ["server/**"]) scoping which
    /// changed files in a commit map to this element. Optional so older /
    /// cached payloads without the columns still decode.
    var repoPaths: [String]?
    /// Optional branch pin — only commits on this branch match this element.
    var repoBranch: String?
    let createdAt: String
    var updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, kind, description, order
        case projectId = "project_id"
        case assignedTo = "assigned_to"
        case assignedName = "assigned_name"
        case repoPaths = "repo_paths"
        case repoBranch = "repo_branch"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// True once the element has at least one glob bound — drives the git badge.
    var hasRepoBinding: Bool { !(repoPaths ?? []).isEmpty }
}

// MARK: - Commit-driven subtask suggestion

/// A Gemini proposal that a local git commit completed a checklist subtask.
/// Surfaced as a chip on the ticket; the user Accepts (flips is_done) or
/// Dismisses. Mirrors the backend `mw_commit_subtask_suggestions` row.
struct MWCommitSuggestion: Identifiable, Codable, Equatable {
    let id: String
    let taskId: String
    let subtaskId: String
    var elementId: String?
    let commitSha: String
    var commitShortSha: String?
    var commitMessage: String?
    var confidence: Double
    var reasoning: String?
    var status: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, status, confidence, reasoning
        case taskId = "task_id"
        case subtaskId = "subtask_id"
        case elementId = "element_id"
        case commitSha = "commit_sha"
        case commitShortSha = "commit_short_sha"
        case commitMessage = "commit_message"
        case createdAt = "created_at"
    }
}

// MARK: - Prop (repo-grounded draft ticket)

/// A "Prop" — a feat|fix draft ticket shaped via repo-grounded chat, promotable
/// to a real kanban ticket. Mirrors `mw_ticket_drafts`.
struct MWTicketDraft: Identifiable, Codable, Equatable {
    let id: String
    let projectId: String
    var elementId: String?
    var kind: String            // "feat" | "fix"
    var title: String?
    var description: String?
    var draftSubtasks: [String]?
    var priority: String
    var status: String          // "draft" | "promoted" | "discarded"
    var promotedTaskId: String?
    let createdAt: String
    var updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, kind, title, description, priority, status
        case projectId = "project_id"
        case elementId = "element_id"
        case draftSubtasks = "draft_subtasks"
        case promotedTaskId = "promoted_task_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var isFeat: Bool { kind == "feat" }
}

/// One message in a Prop's repo-grounded chat. Mirrors `mw_ticket_draft_messages`.
struct MWPropMessage: Identifiable, Codable, Equatable {
    let id: String
    var draftId: String?
    let role: String            // "user" | "assistant" | "system"
    let content: String
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case draftId = "draft_id"
        case createdAt = "created_at"
    }
}

/// Wrapper for the chat turn response (user + assistant messages).
struct MWPropChatTurn: Codable {
    let userMessage: MWPropMessage
    let assistantMessage: MWPropMessage
    enum CodingKeys: String, CodingKey {
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
    }
}

/// Result of an element repo-snapshot sync (server summary).
struct MWSnapshotSummary: Codable {
    let stored: Int
    let skipped: Int
    let totalBytes: Int
    enum CodingKeys: String, CodingKey {
        case stored, skipped
        case totalBytes = "total_bytes"
    }
}

/// Result of a GitHub sync across all bound elements.
struct GitHubSyncResult: Decodable {
    let repo: String?
    let totalStored: Int
    enum CodingKeys: String, CodingKey {
        case repo
        case totalStored = "total_stored"
    }
}

/// A project's GitHub connection (owner/name + branch).
struct GitHubConnection: Codable {
    let repo: String?
    let branch: String?
    let connected: Bool
    var defaultRepo: String?
    var tokenPresent: Bool?
    enum CodingKeys: String, CodingKey {
        case repo, branch, connected
        case defaultRepo = "default_repo"
        case tokenPresent = "token_present"
    }
}
