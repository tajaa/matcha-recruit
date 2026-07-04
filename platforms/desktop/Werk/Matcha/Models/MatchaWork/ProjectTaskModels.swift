import Foundation

// MARK: - Task draft

/// AI-generated ticket draft (Gemini Flash Lite) returned by
/// `POST /projects/{id}/tasks/ai-draft`. Not persisted — the user reviews/edits
/// it in `AIDraftReviewSheet`, then creates via the normal task POST.
struct MWTaskDraft: Codable {
    var title: String
    var description: String?
    var priority: String
    var category: String
    var boardColumn: String
    var assignedTo: String?
    var assignedName: String?
    var elementId: String?
    var elementName: String?
    /// AI-suggested checklist steps. Reviewed/edited in AIDraftReviewSheet, then
    /// created as mw_subtasks after the task on Create.
    var subtasks: [String]?

    enum CodingKeys: String, CodingKey {
        case title, description, priority, category, subtasks
        case boardColumn = "board_column"
        case assignedTo = "assigned_to"
        case assignedName = "assigned_name"
        case elementId = "element_id"
        case elementName = "element_name"
    }
}

/// A note or link pinned to a project element's context repo
/// (`mw_element_notes`). `kind` is "note" (free text in `body`) or "link"
/// (`url` + optional `body` label).
struct MWElementNote: Codable, Identifiable, Hashable {
    let id: String
    var elementId: String?
    var projectId: String?
    var createdBy: String?
    var authorName: String?
    var kind: String
    var body: String?
    var url: String?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, body, url
        case elementId = "element_id"
        case projectId = "project_id"
        case createdBy = "created_by"
        case authorName = "author_name"
        case createdAt = "created_at"
    }
}

/// One row from `mw_task_history` — appears in the TaskViewerSheet
/// timeline. `eventType` is one of: created | column_change |
/// assignee_change | deleted.
struct MWTaskHistoryEntry: Codable, Identifiable, Hashable {
    let id: String
    let taskId: String?
    let actorUserId: String?
    let actorName: String?
    /// users.avatar_url for the actor of this event. Joined server-side from
    /// the users table. nil for system-generated events or users that never
    /// uploaded an avatar (initials fallback handled by ChannelAvatarView).
    let actorAvatarUrl: String?
    let eventType: String
    let fromValue: String?
    let toValue: String?
    let metadata: [String: String]?
    /// mw_project_files row ids tied to THIS note. Server pulls them out of
    /// the metadata JSONB so the client decoder sees a flat field. nil/empty
    /// = a plain text note.
    let attachmentIds: [String]?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case taskId = "task_id"
        case actorUserId = "actor_user_id"
        case actorName = "actor_name"
        case actorAvatarUrl = "actor_avatar_url"
        case eventType = "event_type"
        case fromValue = "from_value"
        case toValue = "to_value"
        case metadata
        case attachmentIds = "attachment_ids"
        case createdAt = "created_at"
    }

    // Custom decode so `metadata` tolerates non-string JSON values. The server
    // stores metadata as JSONB and MOSTLY uses string values, but a stray bool
    // or number (e.g. an event flag) would otherwise fail the WHOLE
    // [MWTaskHistoryEntry] decode — silently emptying a ticket's notes + rounds.
    // Coerce scalars to strings; drop nested objects/arrays/null.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        taskId = try c.decodeIfPresent(String.self, forKey: .taskId)
        actorUserId = try c.decodeIfPresent(String.self, forKey: .actorUserId)
        actorName = try c.decodeIfPresent(String.self, forKey: .actorName)
        actorAvatarUrl = try c.decodeIfPresent(String.self, forKey: .actorAvatarUrl)
        eventType = try c.decode(String.self, forKey: .eventType)
        fromValue = try c.decodeIfPresent(String.self, forKey: .fromValue)
        toValue = try c.decodeIfPresent(String.self, forKey: .toValue)
        metadata = (try? c.decode(LenientStringMap.self, forKey: .metadata))?.values
        attachmentIds = try c.decodeIfPresent([String].self, forKey: .attachmentIds)
        createdAt = try c.decode(String.self, forKey: .createdAt)
    }
}

/// Decodes a JSON object whose values may be strings, bools, or numbers into a
/// `[String: String]`, coercing scalars to their string form and dropping
/// nested containers / null. Keeps one stray non-string value from failing the
/// surrounding decode (see `MWTaskHistoryEntry.init(from:)`).
private struct LenientStringMap: Decodable {
    let values: [String: String]

    private struct DynamicKey: CodingKey {
        var stringValue: String
        var intValue: Int?
        init?(stringValue: String) { self.stringValue = stringValue; self.intValue = nil }
        init?(intValue: Int) { self.stringValue = String(intValue); self.intValue = intValue }
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: DynamicKey.self)
        var out: [String: String] = [:]
        for key in c.allKeys {
            if let s = try? c.decode(String.self, forKey: key) {
                out[key.stringValue] = s
            } else if let b = try? c.decode(Bool.self, forKey: key) {
                out[key.stringValue] = b ? "true" : "false"
            } else if let i = try? c.decode(Int.self, forKey: key) {
                out[key.stringValue] = String(i)
            } else if let d = try? c.decode(Double.self, forKey: key) {
                out[key.stringValue] = String(d)
            }
            // null / nested object / array → skipped
        }
        values = out
    }
}

struct MWProjectTask: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String?
    var title: String
    var description: String?
    var boardColumn: String
    var priority: String
    var status: String
    var assignedTo: String?
    var assignedName: String?
    var assignedEmail: String?
    /// Assignee's profile photo (users.avatar_url), list-query only — nil on
    /// single-task responses/WS payloads, preserved in the VM like the other
    /// list-only aggregates.
    var assignedAvatarUrl: String? = nil
    /// Ticket creator identity for the card-face "created by" avatar badge.
    /// Same list-query-only caveat as assignedAvatarUrl.
    var createdBy: String? = nil
    var createdByName: String? = nil
    var createdByAvatarUrl: String? = nil
    var dueDate: String?
    var completedAt: String?
    var createdAt: String?
    var updatedAt: String?
    var progressNote: String?
    var category: String?
    var elementId: String?
    var elementName: String?
    /// Last time the card crossed columns (from mw_task_history). Null until
    /// the first move. Drives the "Moved …" stamp on the kanban card.
    var lastMovedAt: String?
    var attachments: [MWProjectFile]?

    // ── Pipeline position (independent of kanban board_column) ──
    // Defaults to "lead" on the server; nil until the migration runs.
    var pipelineColumn: String?

    // ── Sales-pipeline fields ──
    // Defaulted to nil so the synthesized memberwise init stays backward-compatible.
    var dealValue: Double? = nil
    var probability: Int? = nil
    var contactName: String? = nil
    var contactCompany: String? = nil
    var contactEmail: String? = nil
    var contactPhone: String? = nil
    var outcome: String? = nil        // open | won | lost
    var lossReason: String? = nil
    var nextActionAt: String? = nil
    var expectedClose: String? = nil

    /// Reviewer's "needs work" note set when a task is sent back from review
    /// to the changes_requested lane. Cleared server-side once it re-enters
    /// review/done. Drives the bounce-back banner in TaskViewerSheet and the
    /// one-line reason on the card face.
    var reviewNote: String? = nil
    /// How many times this card has been sent back from review (count of
    /// `review_rejected` history events). Optional because only the list query
    /// and the reject response carry it — create/update RETURNING clauses
    /// don't. Drives the "↻ ×N" churn chip; treat nil as 0.
    var reviewCycleCount: Int? = nil
    /// Checklist progress, present only on the list query (nil elsewhere).
    /// Card face shows "done/total" with a thin bar. Treat nil as 0.
    var subtaskTotal: Int? = nil
    var subtaskDone: Int? = nil
    /// Unviewed-updates badge inputs, present only on the list query (nil on
    /// create/update/WS payloads — preserved across those in the VM). `update_count`
    /// is the total count of viewable history events; `recentEventIds` are the
    /// newest such event ids, diffed against the per-user viewed set in
    /// TicketUpdatesStore to compute the unviewed count. Treat nil as "unknown".
    var updateCount: Int? = nil
    var recentEventIds: [String]? = nil

    enum CodingKeys: String, CodingKey {
        case id, title, description, priority, status, attachments, category
        case probability, outcome
        case reviewNote = "review_note"
        case reviewCycleCount = "review_cycle_count"
        case subtaskTotal = "subtask_total"
        case subtaskDone = "subtask_done"
        case updateCount = "update_count"
        case recentEventIds = "recent_event_ids"
        case projectId = "project_id"
        case boardColumn = "board_column"
        case pipelineColumn = "pipeline_column"
        case assignedTo = "assigned_to"
        case assignedName = "assigned_name"
        case assignedEmail = "assigned_email"
        case assignedAvatarUrl = "assigned_avatar_url"
        case createdBy = "created_by"
        case createdByName = "created_by_name"
        case createdByAvatarUrl = "created_by_avatar_url"
        case dueDate = "due_date"
        case completedAt = "completed_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case progressNote = "progress_note"
        case lastMovedAt = "last_moved_at"
        case elementId = "element_id"
        case elementName = "element_name"
        case dealValue = "deal_value"
        case contactName = "contact_name"
        case contactCompany = "contact_company"
        case contactEmail = "contact_email"
        case contactPhone = "contact_phone"
        case lossReason = "loss_reason"
        case nextActionAt = "next_action_at"
        case expectedClose = "expected_close"
    }

    /// Convenience for the card chip — "open" when unset.
    var dealOutcome: String { outcome ?? "open" }
}

extension MWProjectTask {
    /// Priority bucket for column ordering (critical highest). Mirrors the
    /// backend `list_project_tasks` ORDER BY and CollabOverview.upcomingTasks().
    var priorityRank: Int {
        switch priority {
        case "critical": return 0
        case "high": return 1
        case "medium": return 2
        case "low": return 3
        default: return 4
        }
    }

    /// Time-since-last-activity bucket. Anchor = lastMovedAt ?? createdAt, so
    /// moving a card between columns resets its clock. Done/completed cards
    /// never age.
    var aging: TaskAging {
        if boardColumn == "done" || status == "completed" { return .none }
        guard let d = PacificDateFormatter.parse(lastMovedAt ?? createdAt) else { return .none }
        let hours = Date().timeIntervalSince(d) / 3600
        if hours >= 12 { return .overdue }
        if hours >= 6 { return .warn }
        return .none
    }

    /// Human-readable assignee label, or nil when no assignee is set.
    /// Prefers the server-provided `assignedName` when it's a real name
    /// (not an email). When the server falls back to email (legacy rows
    /// without a name in clients/employees/admins), derives a name from
    /// the local-part: "jane.doe@…" → "Jane Doe".
    var displayAssignee: String? {
        if let n = assignedName?.trimmingCharacters(in: .whitespaces),
           !n.isEmpty, !n.contains("@") {
            return n
        }
        let raw = assignedEmail ?? assignedName
        guard let local = raw?.split(separator: "@").first.map(String.init),
              !local.isEmpty
        else { return nil }
        return local
            .replacingOccurrences(of: ".", with: " ")
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }
}

/// A checklist item under a kanban task (`mw_subtasks`). Ordered by `position`.
/// Lets a complex feature card decompose into trackable child items; the board
/// shows done/total and a reviewer can re-open specific items on send-back.
struct MWSubtask: Codable, Identifiable, Hashable {
    let id: String
    var taskId: String?
    var projectId: String?
    var title: String
    var isDone: Bool
    var position: Int
    /// Review-cycle round this checklist item belongs to (1 = initial work).
    /// The live checklist shows only the current round; older rounds' items
    /// archive into the rounds history feed. Optional so legacy payloads decode.
    var roundIndex: Int?
    var assignedTo: String?
    var createdBy: String?
    var completedAt: String?
    var createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, position
        case taskId = "task_id"
        case projectId = "project_id"
        case isDone = "is_done"
        case roundIndex = "round_index"
        case assignedTo = "assigned_to"
        case createdBy = "created_by"
        case completedAt = "completed_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}
