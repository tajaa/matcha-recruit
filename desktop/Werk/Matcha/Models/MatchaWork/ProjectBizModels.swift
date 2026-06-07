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
    case feat   // promoted from a "Prop" feature draft
    case fix    // promoted from a "Prop" fix draft

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .engineering: return "Engineering"
        case .sales: return "Sales"
        case .product: return "Product Feature"
        case .bug: return "Bug"
        case .general: return "General"
        case .feat: return "Feature"
        case .fix: return "Fix"
        }
    }

    var icon: String {
        switch self {
        case .engineering: return "hammer"
        case .sales: return "dollarsign.circle"
        case .product: return "sparkles"
        case .bug: return "ant"
        case .general: return "doc.text"
        case .feat: return "sparkles"
        case .fix: return "wrench.and.screwdriver"
        }
    }

    var color: Color {
        switch self {
        case .engineering: return .blue
        case .sales: return .green
        case .product: return .purple
        case .bug: return .red
        case .general: return .secondary
        case .feat: return .teal
        case .fix: return .orange
        }
    }

    var defaultPriority: String {
        switch self {
        case .bug, .fix: return "high"
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
        case .feat:
            return """
            ## What & why
            _The feature and the user value._

            ## Where in the code
            _Files/areas it touches (from the repo chat)._

            ## Steps
            - [ ]
            """
        case .fix:
            return """
            ## Problem
            _What's broken._

            ## Root cause
            _Where in the code (from the repo chat)._

            ## Steps
            - [ ]
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
        case .feat:
            return [
                .init(key: "what", label: "What & why", placeholder: "The feature and the user value.", kind: .multiLine),
                .init(key: "where", label: "Where in the code", placeholder: "Files/areas it touches.", kind: .multiLine),
                .init(key: "steps", label: "Steps", placeholder: "- ", kind: .multiLine),
            ]
        case .fix:
            return [
                .init(key: "problem", label: "Problem", placeholder: "What's broken.", kind: .multiLine),
                .init(key: "rootcause", label: "Root cause", placeholder: "Where in the code.", kind: .multiLine),
                .init(key: "steps", label: "Steps", placeholder: "- ", kind: .multiLine),
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
