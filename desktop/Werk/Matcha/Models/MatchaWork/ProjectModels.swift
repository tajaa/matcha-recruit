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
    var filename: String
    var storageUrl: String
    var contentType: String?
    var fileSize: Int
    var createdAt: String?
    /// nil = root of the Files tab; otherwise the containing folder.
    var folderId: String?

    enum CodingKeys: String, CodingKey {
        case id, filename
        case projectId = "project_id"
        case taskId = "task_id"
        case uploadedBy = "uploaded_by"
        case storageUrl = "storage_url"
        case contentType = "content_type"
        case fileSize = "file_size"
        case createdAt = "created_at"
        case folderId = "folder_id"
    }

    var isImage: Bool {
        if let ct = contentType, ct.lowercased().hasPrefix("image/") { return true }
        let ext = (filename as NSString).pathExtension.lowercased()
        return ["png", "jpg", "jpeg", "gif", "webp", "heic", "svg"].contains(ext)
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

    enum CodingKeys: String, CodingKey {
        case id, name
        case projectId = "project_id"
        case parentId = "parent_id"
        case createdBy = "created_by"
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
    let eventType: String
    let fromValue: String?
    let toValue: String?
    let metadata: [String: String]?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case taskId = "task_id"
        case actorUserId = "actor_user_id"
        case actorName = "actor_name"
        case eventType = "event_type"
        case fromValue = "from_value"
        case toValue = "to_value"
        case metadata
        case createdAt = "created_at"
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

    // ── Sales-pipeline fields ──
    // NULL on normal boards; populated and surfaced only when the project is
    // in pipeline mode. Defaulted to nil so the synthesized memberwise init
    // stays backward-compatible with existing optimistic-construction sites.
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

    enum CodingKeys: String, CodingKey {
        case id, title, description, priority, status, attachments, category
        case probability, outcome
        case projectId = "project_id"
        case boardColumn = "board_column"
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
                let p = Double(t.probability ?? SalesStage.defaultProbability[t.boardColumn] ?? 0)
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

struct MWProject: Codable, Identifiable {
    let id: String
    var title: String
    let projectType: String?
    var status: String?
    var isPinned: Bool?
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
        case id, title, status, version, sections, chats
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

    /// Parse an ISO8601 string, tolerating both fractional-seconds and plain
    /// internet-datetime variants (mirrors TaskClipboardExporter.formatHistoryDate).
    static func parse(_ iso: String?) -> Date? {
        guard let iso, !iso.isEmpty else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: iso) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: iso)
    }

    /// Short Pacific date, e.g. "May 20" (no time). For compact card lines.
    static func shortDate(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        let out = DateFormatter()
        out.timeZone = pacific
        out.dateFormat = "MMM d"
        return out.string(from: date)
    }

    /// Absolute Pacific time, e.g. "May 20, 2:15 PM PT".
    static func absolute(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        let out = DateFormatter()
        out.timeZone = pacific
        out.dateFormat = "MMM d, h:mm a"
        return out.string(from: date) + " PT"
    }

    /// Pacific date + time, e.g. "May 20 at 5:23 PM". For the kanban card
    /// timestamp line so the exact wait-start is visible.
    static func dateTime(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        let out = DateFormatter()
        out.timeZone = pacific
        out.dateFormat = "MMM d 'at' h:mm a"
        return out.string(from: date)
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
        let out = DateFormatter()
        out.timeZone = pacific
        out.dateFormat = "MMM d"
        return out.string(from: date)
    }
}
