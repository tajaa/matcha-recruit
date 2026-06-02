import Foundation
import SwiftUI

// MARK: - Resume Candidate

struct MWResumeCandidate: Codable, Identifiable {
    let id: String
    let filename: String
    let resumeUrl: String?
    let name: String?
    let email: String?
    let phone: String?
    let location: String?
    let currentTitle: String?
    let experienceYears: Double?
    let skills: [String]?
    let education: String?
    let certifications: [String]?
    let summary: String?
    let strengths: [String]?
    let flags: [String]?
    let status: String?
    let interviewId: String?
    let interviewStatus: String?
    let interviewScore: Double?
    let interviewSummary: String?
    let matchScore: Double?
    let matchSummary: String?

    enum CodingKeys: String, CodingKey {
        case id, filename, name, email, phone, location, skills, education
        case certifications, summary, strengths, flags, status
        case resumeUrl = "resume_url"
        case currentTitle = "current_title"
        case experienceYears = "experience_years"
        case interviewId = "interview_id"
        case interviewStatus = "interview_status"
        case interviewScore = "interview_score"
        case interviewSummary = "interview_summary"
        case matchScore = "match_score"
        case matchSummary = "match_summary"
    }

    var displayName: String { name ?? filename }
}

struct MWSendInterviewsRequest: Codable {
    let candidateIds: [String]
    let positionTitle: String?
    let customMessage: String?

    enum CodingKeys: String, CodingKey {
        case candidateIds = "candidate_ids"
        case positionTitle = "position_title"
        case customMessage = "custom_message"
    }
}

// MARK: - Inventory Item

struct MWInventoryItem: Codable, Identifiable {
    let id: String
    let filename: String
    let productName: String?
    let sku: String?
    let category: String?
    let quantity: Double?
    let unit: String?
    let unitCost: Double?
    let totalCost: Double?
    let vendor: String?
    let parLevel: Double?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case id, filename, sku, category, quantity, unit, vendor, status
        case productName = "product_name"
        case unitCost = "unit_cost"
        case totalCost = "total_cost"
        case parLevel = "par_level"
    }

    var displayName: String { productName ?? filename }
}

// MARK: - Projects

enum MWProjectType: String, Codable {
    case general
    case presentation
    case recruiting
    case collab
}

struct MWProjectFile: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String?
    var taskId: String?
    var uploadedBy: String?
    /// Display name of the uploader (joined server-side from users/clients/
    /// employees/admins). nil when no uploader is recorded.
    var uploaderName: String?
    /// users.avatar_url for the uploader. Drives the pfp on attachment rows.
    var uploaderAvatarUrl: String?
    var filename: String
    var storageUrl: String
    var contentType: String?
    var fileSize: Int
    var createdAt: String?
    /// nil = root of the Files tab; otherwise the containing folder.
    var folderId: String?
    /// nil = project root Files/Media; otherwise bucketed under an element repo.
    var elementId: String?
    /// Review round this file was uploaded in (1-based). Only populated by the
    /// per-task files endpoint (derived server-side from upload time vs the
    /// task's round boundaries); nil on other file lists. Lets the ticket
    /// viewer keep the current round's attachments in the foreground.
    var roundIndex: Int?

    enum CodingKeys: String, CodingKey {
        case id, filename
        case projectId = "project_id"
        case taskId = "task_id"
        case uploadedBy = "uploaded_by"
        case uploaderName = "uploader_name"
        case uploaderAvatarUrl = "uploader_avatar_url"
        case storageUrl = "storage_url"
        case contentType = "content_type"
        case fileSize = "file_size"
        case createdAt = "created_at"
        case folderId = "folder_id"
        case elementId = "element_id"
        case roundIndex = "round_index"
    }

    var isImage: Bool {
        if let ct = contentType, ct.lowercased().hasPrefix("image/") { return true }
        let ext = (filename as NSString).pathExtension.lowercased()
        return ["png", "jpg", "jpeg", "gif", "webp", "heic", "svg"].contains(ext)
    }
}

/// A link shared in the project's collab chat (http(s) URL pulled from a
/// message). Not a file — surfaced in the Media tab's "Links" bucket.
struct MWProjectLink: Codable, Identifiable, Hashable {
    let url: String
    var senderName: String?
    var createdAt: String?

    var id: String { url }

    enum CodingKeys: String, CodingKey {
        case url
        case senderName = "sender_name"
        case createdAt = "created_at"
    }
}

/// A folder in a project's Files tab. `parentId` nil = top level.
struct MWProjectFolder: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String?
    var parentId: String?
    var name: String
    var createdBy: String?
    var createdAt: String?
    /// nil = a root Files-tab folder; otherwise part of an element's repo tree.
    var elementId: String?

    enum CodingKeys: String, CodingKey {
        case id, name
        case projectId = "project_id"
        case parentId = "parent_id"
        case createdBy = "created_by"
        case createdAt = "created_at"
        case elementId = "element_id"
    }
}

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

/// One row from the project-scoped activity feed
/// (`/projects/{id}/activity`). `source` discriminates the payload
/// shape: task_history | file_upload | collaborator_added.
struct MWProjectActivityEntry: Codable, Identifiable {
    let source: String
    let actorUserId: String?
    let actorName: String?
    let createdAt: String
    let payload: [String: AnyCodable]

    var id: String { "\(source)-\(createdAt)-\(actorUserId ?? "?")" }

    enum CodingKeys: String, CodingKey {
        case source
        case actorUserId = "actor_user_id"
        case actorName = "actor_name"
        case createdAt = "created_at"
        case payload
    }

    /// Best-effort string accessor for payload keys. Most values arrive
    /// as String / Int from PG's jsonb_build_object; fall back to a
    /// cast via NSString-coercion for anything else.
    func string(_ key: String) -> String? {
        guard let v = payload[key]?.value else { return nil }
        if let s = v as? String { return s }
        if v is NSNull { return nil }
        return "\(v)"
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

// MARK: - Sales pipeline

/// Fixed sales-pipeline stages, used in place of the default kanban columns
/// when a project is in pipeline mode. Keys are stored in
/// `mw_tasks.board_column`. `defaultProbability` seeds a new deal's win
/// likelihood from its stage (editable per deal).
enum SalesStage {
    static let columns: [(key: String, label: String)] = [
        ("lead", "Lead"),
        ("qualified", "Qualified"),
        ("proposal", "Proposal"),
        ("negotiation", "Negotiation"),
        ("closed", "Closed"),
    ]
    static let keys: Set<String> = Set(columns.map { $0.key })
    static let defaultProbability: [String: Int] = [
        "lead": 10, "qualified": 30, "proposal": 60, "negotiation": 80, "closed": 100,
    ]
}

/// Aggregate sales metrics over a board's tasks, computed client-side (the
/// board already holds every task in memory, so no extra round-trip).
struct PipelineSummary {
    var openCount = 0
    var wonCount = 0
    var lostCount = 0
    var openValue: Double = 0       // Σ deal_value of open deals
    var weightedValue: Double = 0   // Σ deal_value × probability/100 of open deals
    var wonValue: Double = 0        // Σ deal_value of won deals

    /// won / (won + lost); 0 when nothing has been decided yet.
    var winRate: Double {
        let decided = wonCount + lostCount
        return decided == 0 ? 0 : Double(wonCount) / Double(decided)
    }

    init(tasks: [MWProjectTask]) {
        for t in tasks {
            let value = t.dealValue ?? 0
            switch t.dealOutcome {
            case "won":
                wonCount += 1
                wonValue += value
            case "lost":
                lostCount += 1
            default:
                openCount += 1
                openValue += value
                let p = Double(t.probability ?? SalesStage.defaultProbability[t.pipelineColumn ?? "lead"] ?? 0)
                weightedValue += value * p / 100.0
            }
        }
    }
}

extension MWProject {
    /// Sales-pipeline mode is opt-in per project, stored in
    /// `project_data.pipeline_mode` (merged server-side, see
    /// matcha_work `PATCH /projects/{id}/pipeline-mode`).
    var pipelineMode: Bool {
        guard let raw = projectData?["pipeline_mode"]?.value else { return false }
        if let b = raw as? Bool { return b }
        if let i = raw as? Int { return i != 0 }
        if let s = raw as? String { return s == "true" || s == "1" }
        return false
    }
}

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
    let createdAt: String
    var updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, kind, description, order
        case projectId = "project_id"
        case assignedTo = "assigned_to"
        case assignedName = "assigned_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

/// Time-since-last-activity bucket driving the kanban card header tint.
/// none → no tint, warn → orange, overdue → red.
enum TaskAging { case none, warn, overdue }

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

/// SF Symbols offered in the project icon picker (mirrors the journal grid).
/// `"folder"` is the default fallback when a project has no chosen icon.
let mwProjectIconOptions = [
    "folder", "doc.text", "list.bullet.clipboard", "briefcase",
    "lightbulb", "chart.bar.xaxis", "paintbrush", "hammer",
    "megaphone", "calendar", "star", "flag",
]

struct MWProject: Codable, Identifiable {
    let id: String
    var title: String
    let projectType: String?
    var status: String?
    var isPinned: Bool?
    var icon: String?
    var version: Int?
    var sections: [MWProjectSection]?
    var projectData: [String: AnyCodable]?
    var chatCount: Int?
    var chats: [MWProjectChat]?
    var collaborators: [MWProjectCollaborator]?
    var collaboratorRole: String?
    let createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version, sections, chats, icon
        case projectType = "project_type"
        case isPinned = "is_pinned"
        case projectData = "project_data"
        case chatCount = "chat_count"
        case collaborators
        case collaboratorRole = "collaborator_role"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

/// One-shot project-open payload (GET /matcha-work/projects/{id}/bundle):
/// project detail + every per-project sub-resource in a single response, so a
/// cold collab-project open is one round-trip instead of ~6. Top-level keys map
/// 1:1 to the individual endpoints; each field reuses that endpoint's model.
struct MWProjectBundle: Codable {
    let project: MWProject
    let tasks: [MWProjectTask]
    let files: [MWProjectFile]
    let folders: [MWProjectFolder]
    let links: [MWProjectLink]
    let collaborators: [MWProjectCollaborator]
    let elements: [MWProjectElement]
}

struct MWProjectChat: Codable, Identifiable, Hashable {
    let id: String
    var title: String
    var status: String?
    var version: Int?
    var createdAt: String?
    var updatedAt: String?
    var isPinned: Bool?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case isPinned = "is_pinned"
    }
}

struct MWSectionHistoryEntry: Codable, Identifiable {
    var id: String { at }
    let content: String
    let source: String?
    let at: String
    /// Who authored this (now-superseded) content. Older snapshots predate
    /// attribution and carry nil — fall back to `source` for display.
    let authorId: String?
    let authorName: String?

    enum CodingKeys: String, CodingKey {
        case content, source, at
        case authorId = "author_id"
        case authorName = "author_name"
    }
}

struct MWProjectSection: Codable, Identifiable {
    let id: String
    var title: String
    var content: String?
    var sourceMessageId: String?
    var pendingRevision: String?
    var pendingChangeSummary: String?
    var contentSource: String?
    var contentUpdatedAt: String?
    var history: [MWSectionHistoryEntry]?
    /// Who last wrote the current content + when — drives "Last edited by X".
    var lastEditedBy: String?
    var lastEditedByName: String?
    var lastEditedAt: String?

    var hasPendingRevision: Bool {
        !(pendingRevision?.isEmpty ?? true)
    }

    enum CodingKeys: String, CodingKey {
        case id, title, content, history
        case sourceMessageId = "source_message_id"
        case pendingRevision = "pending_revision"
        case pendingChangeSummary = "pending_change_summary"
        case contentSource = "content_source"
        case contentUpdatedAt = "content_updated_at"
        case lastEditedBy = "last_edited_by"
        case lastEditedByName = "last_edited_by_name"
        case lastEditedAt = "last_edited_at"
    }

    // Tolerate `title: null` in legacy section data — historical AI output
    // wrote untitled sections that way. A non-optional `String` decode of
    // null would otherwise fail the entire mw_projects list and present
    // as "No projects yet". Treat null/missing as empty string so call
    // sites (Text, isEmpty checks) keep working unchanged.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = (try? c.decodeIfPresent(String.self, forKey: .title)) ?? ""
        content = try c.decodeIfPresent(String.self, forKey: .content)
        sourceMessageId = try c.decodeIfPresent(String.self, forKey: .sourceMessageId)
        pendingRevision = try c.decodeIfPresent(String.self, forKey: .pendingRevision)
        pendingChangeSummary = try c.decodeIfPresent(String.self, forKey: .pendingChangeSummary)
        contentSource = try c.decodeIfPresent(String.self, forKey: .contentSource)
        contentUpdatedAt = try c.decodeIfPresent(String.self, forKey: .contentUpdatedAt)
        history = try c.decodeIfPresent([MWSectionHistoryEntry].self, forKey: .history)
        lastEditedBy = try c.decodeIfPresent(String.self, forKey: .lastEditedBy)
        lastEditedByName = try c.decodeIfPresent(String.self, forKey: .lastEditedByName)
        lastEditedAt = try c.decodeIfPresent(String.self, forKey: .lastEditedAt)
    }
}

/// An in-app comment on a project note (section). Author name + avatar are
/// resolved server-side so the client can render without an extra join.
struct MWSectionComment: Codable, Identifiable, Hashable {
    let id: String
    var sectionId: String?
    var userId: String
    var authorName: String?
    var avatarUrl: String?
    var content: String
    var replyToCommentId: String?
    /// Highlight anchor: UTF-16 char range into the note text. Both nil for a
    /// general (whole-note) comment. `quotedText` is the snippet at creation
    /// time, used to re-find the range if the text shifted.
    var anchorStart: Int?
    var anchorEnd: Int?
    var quotedText: String?
    var resolved: Bool?
    var createdAt: String?

    /// True when this comment is pinned to a text range (vs a general comment).
    var isAnchored: Bool { anchorStart != nil && anchorEnd != nil }
    var isResolved: Bool { resolved ?? false }

    enum CodingKeys: String, CodingKey {
        case id, content, resolved
        case sectionId = "section_id"
        case userId = "user_id"
        case authorName = "author_name"
        case avatarUrl = "avatar_url"
        case replyToCommentId = "reply_to_comment_id"
        case anchorStart = "anchor_start"
        case anchorEnd = "anchor_end"
        case quotedText = "quoted_text"
        case createdAt = "created_at"
    }
}

struct MWProjectCollaborator: Codable, Identifiable {
    var id: String { userId }
    let userId: String
    let name: String
    let email: String
    let avatarUrl: String?
    let role: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case name, email, role
        case userId = "user_id"
        case avatarUrl = "avatar_url"
        case createdAt = "created_at"
    }
}

// MARK: - Recruiting Project Helpers

struct MWJobPosting: Codable {
    var title: String?
    var content: String?
    var finalized: Bool?

    enum CodingKeys: String, CodingKey {
        case title, content, finalized
    }
}

/// View-model helper that decodes/encodes the recruiting slice of `project_data`.
/// Round-trips via `JSONSerialization` over the `AnyCodable` blob stored on `MWProject`.
struct MWRecruitingData {
    var posting: MWJobPosting
    var candidates: [MWResumeCandidate]
    var shortlistIds: Set<String>
    var dismissedIds: Set<String>

    static func from(projectData: [String: AnyCodable]?) -> MWRecruitingData {
        var posting = MWJobPosting(title: nil, content: nil, finalized: false)
        var candidates: [MWResumeCandidate] = []
        var shortlist: Set<String> = []
        var dismissed: Set<String> = []

        guard let data = projectData else {
            return MWRecruitingData(posting: posting, candidates: candidates,
                                    shortlistIds: shortlist, dismissedIds: dismissed)
        }

        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        func decode<T: Decodable>(_ key: String, as type: T.Type) -> T? {
            guard let any = data[key] else { return nil }
            guard let json = try? encoder.encode(any) else { return nil }
            return try? decoder.decode(T.self, from: json)
        }

        if let decoded: MWJobPosting = decode("posting", as: MWJobPosting.self) {
            posting = decoded
        }
        if let decoded: [MWResumeCandidate] = decode("candidates", as: [MWResumeCandidate].self) {
            candidates = decoded
        }
        if let ids: [String] = decode("shortlist_ids", as: [String].self) {
            shortlist = Set(ids)
        }
        if let ids: [String] = decode("dismissed_ids", as: [String].self) {
            dismissed = Set(ids)
        }

        return MWRecruitingData(posting: posting, candidates: candidates,
                                shortlistIds: shortlist, dismissedIds: dismissed)
    }
}

struct MWAdminSearchUser: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, email, name
        case avatarUrl = "avatar_url"
    }
}

// MARK: - Blog (project_type == "blog")

struct MWBlogAuthor: Codable, Hashable {
    var name: String?
    var bio: String?
    var avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case name, bio
        case avatarUrl = "avatar_url"
    }
}

struct MWBlogData {
    var slug: String
    var excerpt: String
    var status: String          // draft | scheduled | published
    var tone: String
    var audience: String
    var tags: [String]
    var author: MWBlogAuthor
    var wordCount: Int
    var readMinutes: Int
    var publishedAt: String?
    var coverImageUrl: String?
    var scheduledFor: String?

    static func from(projectData: [String: AnyCodable]?) -> MWBlogData {
        let data = projectData ?? [:]
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        func decode<T: Decodable>(_ key: String, as type: T.Type) -> T? {
            guard let any = data[key] else { return nil }
            guard let json = try? encoder.encode(any) else { return nil }
            return try? decoder.decode(T.self, from: json)
        }

        let author = decode("author", as: MWBlogAuthor.self) ?? MWBlogAuthor()
        let tags: [String]
        if let ts = data["tags"]?.value as? [String] {
            tags = ts
        } else if let ts = data["tags"]?.value as? [AnyCodable] {
            tags = ts.compactMap { $0.value as? String }
        } else {
            tags = []
        }

        return MWBlogData(
            slug: data["slug"]?.value as? String ?? "",
            excerpt: data["excerpt"]?.value as? String ?? "",
            status: data["status"]?.value as? String ?? "draft",
            tone: data["tone"]?.value as? String ?? "expert-casual",
            audience: data["audience"]?.value as? String ?? "",
            tags: tags,
            author: author,
            wordCount: data["word_count"]?.value as? Int ?? 0,
            readMinutes: data["read_minutes"]?.value as? Int ?? 1,
            publishedAt: data["published_at"]?.value as? String,
            coverImageUrl: data["cover_image_url"]?.value as? String,
            scheduledFor: data["scheduled_for"]?.value as? String
        )
    }
}

struct MWBlogPatchRequest: Codable {
    var slug: String?
    var excerpt: String?
    var tone: String?
    var audience: String?
    var tags: [String]?
    var author: MWBlogAuthor?
}

struct MWBlogStatusRequest: Codable {
    var status: String
}

// MARK: - Dashboard models

/// Cross-project pending task surfaced on the Home dashboard.
struct MWOpenTask: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String?
    var projectTitle: String?
    var projectType: String?
    var title: String
    var priority: String
    var status: String
    var dueDate: String?
    var progressNote: String?
    var assignedTo: String?
    var createdBy: String?
    var updatedAt: String?
    /// True for checklist subtasks (mw_subtasks) merged into the list; nil/false
    /// for top-level tasks. Optional so older payloads still decode.
    var isSubtask: Bool?
    /// Parent task id + title — present only on subtask rows.
    var parentTaskId: String?
    var parentTitle: String?

    enum CodingKeys: String, CodingKey {
        case id, title, priority, status
        case projectId = "project_id"
        case projectTitle = "project_title"
        case projectType = "project_type"
        case dueDate = "due_date"
        case progressNote = "progress_note"
        case assignedTo = "assigned_to"
        case createdBy = "created_by"
        case updatedAt = "updated_at"
        case isSubtask = "is_subtask"
        case parentTaskId = "parent_task_id"
        case parentTitle = "parent_title"
    }
}

/// Recent-activity feed item for the Home dashboard.
struct MWActivityItem: Codable, Identifiable, Hashable {
    let kind: String        // "project" | "task" | "thread"
    let refId: String
    var projectId: String?
    var title: String
    var projectType: String?
    var updatedAt: String?

    /// Identifiable: kind+refId is unique across the union'd feed.
    var id: String { "\(kind):\(refId)" }

    enum CodingKeys: String, CodingKey {
        case kind, title
        case refId = "ref_id"
        case projectId = "project_id"
        case projectType = "project_type"
        case updatedAt = "updated_at"
    }
}

struct MWProjectInvite: Codable, Identifiable {
    var id: String { projectId }
    let projectId: String
    let projectTitle: String
    let invitedBy: String
    let invitedAt: String?

    enum CodingKeys: String, CodingKey {
        case projectId = "project_id"
        case projectTitle = "project_title"
        case invitedBy = "invited_by"
        case invitedAt = "invited_at"
    }
}

// MARK: - Kanban ticket templates

/// Built-in ticket starting points. The rawValue is the wire string stored in
/// `mw_tasks.category`; `manual` (blank task / legacy rows) maps to no
/// template, so `from(category:)` returns nil and the card shows no badge.
enum KanbanTemplate: String, CaseIterable, Identifiable {
    case engineering
    case sales
    case product
    case bug
    case general

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .engineering: return "Engineering"
        case .sales: return "Sales"
        case .product: return "Product Feature"
        case .bug: return "Bug"
        case .general: return "General"
        }
    }

    var icon: String {
        switch self {
        case .engineering: return "hammer"
        case .sales: return "dollarsign.circle"
        case .product: return "sparkles"
        case .bug: return "ant"
        case .general: return "doc.text"
        }
    }

    var color: Color {
        switch self {
        case .engineering: return .blue
        case .sales: return .green
        case .product: return .purple
        case .bug: return .red
        case .general: return .secondary
        }
    }

    var defaultPriority: String {
        switch self {
        case .bug: return "high"
        default: return "medium"
        }
    }

    /// Markdown description starter prefilled into the compose sheet. Italic
    /// `_prompts_` are inline guidance the author replaces or deletes.
    var scaffold: String {
        switch self {
        case .engineering:
            return """
            ## Context
            _What's the problem and why now?_

            ## Scope
            - [ ] \n- [ ]

            ## Acceptance criteria
            - [ ]

            ## Technical notes
            _Approach, affected files/services, risks._

            ## Out of scope
            -
            """
        case .sales:
            return """
            ## Account
            _Company · contact · role_

            ## Opportunity
            _Deal size · timeline · source_

            ## Stage
            _Prospecting / Demo / Proposal / Negotiation / Closing_

            ## Pain / need
            -

            ## Next step
            - [ ]

            ## Blockers
            -
            """
        case .product:
            return """
            ## Problem
            _Who hurts, and how today?_

            ## User story
            As a _____, I want _____ so that _____.

            ## Proposed solution
            -

            ## Success metric
            _How we'll know it worked._

            ## Open questions
            -

            ## Out of scope
            -
            """
        case .bug:
            return """
            ## Summary
            _One line._

            ## Environment
            _Build / OS / device_

            ## Steps to reproduce
            1. \n2.

            ## Expected
            -

            ## Actual
            -

            ## Severity / impact
            _Who's affected, how often._

            ## Evidence
            _Screenshots / logs — drag files onto the ticket._
            """
        case .general:
            return """
            ## Goal
            -

            ## Tasks
            - [ ]

            ## Notes
            -
            """
        }
    }

    /// One labeled input rendered in the compose sheet. The label doubles as
    /// the `## Heading` in the composed markdown description.
    struct TicketField: Identifiable {
        enum Kind: Equatable {
            case singleLine
            case multiLine
            case picker([String])
        }
        let key: String          // stable identity
        let label: String        // shown in the form + used as markdown heading
        let placeholder: String
        let kind: Kind
        var id: String { key }
    }

    /// Structured fields shown in the compose sheet, per template. Replaces the
    /// raw-markdown scaffold so the author fills labeled inputs instead of
    /// deleting placeholder text. `general` (and the blank/manual path) use a
    /// single free-form Description box for back-compat.
    var fields: [TicketField] {
        switch self {
        case .engineering:
            return [
                .init(key: "context", label: "Context", placeholder: "What's the problem and why now?", kind: .multiLine),
                .init(key: "scope", label: "Scope", placeholder: "- \n- ", kind: .multiLine),
                .init(key: "acceptance", label: "Acceptance criteria", placeholder: "- ", kind: .multiLine),
                .init(key: "technical", label: "Technical notes", placeholder: "Approach, affected files/services, risks.", kind: .multiLine),
                .init(key: "outofscope", label: "Out of scope", placeholder: "What this explicitly does not cover.", kind: .multiLine),
            ]
        case .sales:
            return [
                .init(key: "account", label: "Account", placeholder: "Company · contact · role", kind: .singleLine),
                .init(key: "opportunity", label: "Opportunity", placeholder: "Deal size · timeline · source", kind: .singleLine),
                .init(key: "stage", label: "Stage", placeholder: "", kind: .picker(["Prospecting", "Demo", "Proposal", "Negotiation", "Closing"])),
                .init(key: "pain", label: "Pain / need", placeholder: "What hurts today?", kind: .multiLine),
                .init(key: "nextstep", label: "Next step", placeholder: "The single next action.", kind: .singleLine),
                .init(key: "blockers", label: "Blockers", placeholder: "What's in the way?", kind: .multiLine),
            ]
        case .product:
            return [
                .init(key: "problem", label: "Problem", placeholder: "Who hurts, and how today?", kind: .multiLine),
                .init(key: "userstory", label: "User story", placeholder: "As a ___, I want ___ so that ___.", kind: .multiLine),
                .init(key: "solution", label: "Proposed solution", placeholder: "", kind: .multiLine),
                .init(key: "metric", label: "Success metric", placeholder: "How we'll know it worked.", kind: .singleLine),
                .init(key: "questions", label: "Open questions", placeholder: "", kind: .multiLine),
                .init(key: "outofscope", label: "Out of scope", placeholder: "", kind: .multiLine),
            ]
        case .bug:
            return [
                .init(key: "summary", label: "Summary", placeholder: "One line.", kind: .singleLine),
                .init(key: "environment", label: "Environment", placeholder: "Build / OS / device", kind: .singleLine),
                .init(key: "steps", label: "Steps to reproduce", placeholder: "1. \n2. ", kind: .multiLine),
                .init(key: "expected", label: "Expected", placeholder: "What should happen.", kind: .multiLine),
                .init(key: "actual", label: "Actual", placeholder: "What happens instead.", kind: .multiLine),
                .init(key: "severity", label: "Severity / impact", placeholder: "", kind: .picker(["Critical", "High", "Medium", "Low"])),
                .init(key: "evidence", label: "Evidence", placeholder: "Screenshots / logs — drag files onto the ticket.", kind: .multiLine),
            ]
        case .general:
            return [
                .init(key: "description", label: "Description", placeholder: "What needs to happen?", kind: .multiLine),
            ]
        }
    }

    /// Builds the markdown `description` from filled compose-sheet field values.
    /// Empty fields are skipped. A lone free-form "description" field
    /// (general/manual) is emitted as plain text with no heading so it reads
    /// naturally; everything else becomes `## Label\n<value>` blocks — the same
    /// on-disk format the viewer/edit/copy paths already expect.
    static func composeDescription(fields: [TicketField], values: [String: String]) -> String {
        if fields.count == 1, fields[0].key == "description" {
            return (values["description"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var blocks: [String] = []
        for f in fields {
            let v = (values[f.key] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !v.isEmpty else { continue }
            blocks.append("## \(f.label)\n\(v)")
        }
        return blocks.joined(separator: "\n\n")
    }

    /// Maps a stored `category` string back to a template for badge rendering.
    /// Returns nil for "manual"/unknown so those cards render without a badge.
    static func from(category: String?) -> KanbanTemplate? {
        guard let category, category != "manual" else { return nil }
        return KanbanTemplate(rawValue: category)
    }
}

// MARK: - Pacific-time formatting

/// Formats ISO8601 UTC timestamp strings into Pacific-time display strings for
/// kanban cards / the task viewer. Uses America/Los_Angeles so PST/PDT is
/// handled automatically.
enum PacificDateFormatter {
    private static let pacific = TimeZone(identifier: "America/Los_Angeles") ?? .current

    // Formatters are expensive to allocate (each builds ICU state, ~10–50µs).
    // The kanban board parses/formats timestamps inside a GeometryReader that
    // re-evaluates every frame on window resize, across every card and every
    // sort comparison — allocating per call pinned resize to ~11fps. These are
    // reused statics instead. Two ISO parsers (one per formatOptions variant)
    // so nothing mutates `formatOptions` at call time, which keeps them safe to
    // share; DateFormatter read methods are documented thread-safe likewise.
    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private static func makeFormatter(_ format: String) -> DateFormatter {
        let f = DateFormatter()
        f.timeZone = pacific
        f.dateFormat = format
        return f
    }
    private static let shortFmt = makeFormatter("MMM d")
    private static let absoluteFmt = makeFormatter("MMM d, h:mm a")
    private static let dateTimeFmt = makeFormatter("MMM d 'at' h:mm a")

    /// Parse an ISO8601 string, tolerating both fractional-seconds and plain
    /// internet-datetime variants (mirrors TaskClipboardExporter.formatHistoryDate).
    static func parse(_ iso: String?) -> Date? {
        guard let iso, !iso.isEmpty else { return nil }
        return isoFractional.date(from: iso) ?? isoPlain.date(from: iso)
    }

    /// Short Pacific date, e.g. "May 20" (no time). For compact card lines.
    static func shortDate(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        return shortFmt.string(from: date)
    }

    /// Absolute Pacific time, e.g. "May 20, 2:15 PM PT".
    static func absolute(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        return absoluteFmt.string(from: date) + " PT"
    }

    /// Pacific date + time, e.g. "May 20 at 5:23 PM". For the kanban card
    /// timestamp line so the exact wait-start is visible.
    static func dateTime(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        return dateTimeFmt.string(from: date)
    }

    /// Compact relative ("just now", "2h ago", "3d ago"); falls back to a short
    /// absolute Pacific date past 7 days.
    static func relative(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        let secs = Int(Date().timeIntervalSince(date))
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(secs / 60)m ago" }
        if secs < 86400 { return "\(secs / 3600)h ago" }
        if secs < 7 * 86400 { return "\(secs / 86400)d ago" }
        return shortFmt.string(from: date)
    }
}
