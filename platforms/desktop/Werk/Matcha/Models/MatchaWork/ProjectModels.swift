import Foundation
import SwiftUI

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

/// Time-since-last-activity bucket driving the kanban card header tint.
/// none → no tint, warn → orange, overdue → red.
enum TaskAging { case none, warn, overdue }

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
    /// Connected GitHub repo (owner/name) + branch, for commit-scan + Prop
    /// code grounding. nil = not connected.
    var githubRepo: String?
    var githubBranch: String?
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
        case githubRepo = "github_repo"
        case githubBranch = "github_branch"
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
    private static let timeOnlyFmt = makeFormatter("h:mm a")

    /// Monday-first Pacific calendar, shared by the week-boundary helpers
    /// below. A fresh `Calendar` per call is cheap (unlike DateFormatter,
    /// no ICU pattern compilation) so this isn't cached as a static.
    private static var pacificCalendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = pacific
        cal.firstWeekday = 2 // Monday
        return cal
    }

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

    /// Time only, e.g. "2:14 PM". Used for the replay scrub-position label.
    static func timeOnly(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        return timeOnlyFmt.string(from: date)
    }

    /// Monday 12:00am Pacific of the week containing `date` — the Weekly
    /// Replay boundary. Sunday 11:59:59pm is implicitly `startOfWeek + 7 days`
    /// (the server derives `week_end` the same way; nothing computes it here).
    static func startOfWeek(containing date: Date) -> Date {
        let cal = pacificCalendar
        let comps = cal.dateComponents([.yearForWeekOfYear, .weekOfYear], from: date)
        return cal.date(from: comps) ?? date
    }

    /// "Jun 30 – Jul 6" for the week-picker header. Both ends computed from
    /// the same Pacific calendar as `startOfWeek` so they never drift a day
    /// apart across a DST transition.
    static func weekLabel(_ start: Date) -> String {
        let cal = pacificCalendar
        let end = cal.date(byAdding: .day, value: 6, to: start) ?? start
        return "\(shortFmt.string(from: start)) – \(shortFmt.string(from: end))"
    }
}
