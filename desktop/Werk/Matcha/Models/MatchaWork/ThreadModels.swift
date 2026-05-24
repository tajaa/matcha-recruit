import Foundation

enum MWTaskType: String, Codable {
    case offerLetter = "offer_letter"
    case review
    case workbook
    case onboarding
    case presentation
    case handbook
    case resumeBatch = "resume_batch"
    case inventory
    case policy
    case project
    case blog
    case languageTutor = "language_tutor"
    case chat

    var label: String {
        switch self {
        case .chat: return "chat"
        case .review: return "anonymized review"
        case .workbook: return "HR workbook"
        case .onboarding: return "employee onboarding"
        case .presentation: return "presentation"
        case .handbook: return "employee handbook"
        case .offerLetter: return "offer letter"
        case .resumeBatch: return "resume batch"
        case .inventory: return "inventory"
        case .policy: return "policy"
        case .project: return "project"
        case .blog: return "blog"
        case .languageTutor: return "language tutor"
        }
    }

    var icon: String {
        switch self {
        case .chat: return "bubble.left"
        case .review: return "doc.text.magnifyingglass"
        case .workbook: return "book.closed"
        case .onboarding: return "person.badge.plus"
        case .presentation: return "rectangle.on.rectangle"
        case .handbook: return "book"
        case .offerLetter: return "doc.badge.plus"
        case .resumeBatch: return "person.2"
        case .inventory: return "list.bullet"
        case .policy: return "shield"
        case .project: return "folder"
        case .blog: return "pencil.line"
        case .languageTutor: return "character.bubble"
        }
    }

    // Backend may introduce new skill values ahead of the client. Fall back to
    // `.chat` instead of throwing so thread loads don't fail on unknown values.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MWTaskType(rawValue: raw) ?? .chat
    }
}

func inferMWTaskType(from state: [String: AnyCodable]) -> MWTaskType {
    if state["candidate_name"] != nil || state["position_title"] != nil || state["salary"] != nil {
        return .offerLetter
    }
    if state["overall_rating"] != nil || state["review_title"] != nil || state["review_request_statuses"] != nil {
        return .review
    }
    if state.keys.contains(where: { $0.hasPrefix("handbook_") }) {
        return .handbook
    }
    if state["candidates"] != nil || state["batch_title"] != nil || state["batch_status"] != nil {
        return .resumeBatch
    }
    if state["inventory_items"] != nil || state["inventory_title"] != nil {
        return .inventory
    }
    if state["sections"] != nil || state["workbook_title"] != nil {
        return .workbook
    }
    if state["presentation_title"] != nil || state["slides"] != nil {
        return .presentation
    }
    if state["employees"] != nil {
        return .onboarding
    }
    return .chat
}

struct MWThread: Codable, Identifiable {
    let id: String
    var title: String
    var taskType: MWTaskType?
    var status: String
    var version: Int
    var isPinned: Bool
    var nodeMode: Bool
    var complianceMode: Bool
    var payerMode: Bool
    let createdAt: String
    var updatedAt: String?
    // Present on project-scoped thread listings; nil elsewhere. Used to render
    // the "Shared" badge and gate the owner-only Share action in collab projects.
    var createdBy: String?
    var collaboratorCount: Int?

    var resolvedTaskType: MWTaskType {
        taskType ?? .chat
    }

    var lastActivityAt: String {
        updatedAt ?? createdAt
    }

    enum CodingKeys: String, CodingKey {
        case id, title, status, version
        case taskType = "task_type"
        case isPinned = "is_pinned"
        case nodeMode = "node_mode"
        case complianceMode = "compliance_mode"
        case payerMode = "payer_mode"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case createdBy = "created_by"
        case collaboratorCount = "collaborator_count"
    }
}

struct MWCreateThreadResponse: Codable {
    let id: String
    let title: String
    let taskType: MWTaskType?
    let status: String
    let currentState: [String: AnyCodable]
    let version: Int
    let isPinned: Bool
    let nodeMode: Bool?
    let complianceMode: Bool?
    let payerMode: Bool?
    let createdAt: String
    let assistantReply: String?
    let pdfUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version
        case taskType = "task_type"
        case currentState = "current_state"
        case isPinned = "is_pinned"
        case nodeMode = "node_mode"
        case complianceMode = "compliance_mode"
        case payerMode = "payer_mode"
        case createdAt = "created_at"
        case assistantReply = "assistant_reply"
        case pdfUrl = "pdf_url"
    }

    func toThread() -> MWThread {
        MWThread(id: id, title: title, taskType: taskType, status: status,
                 version: version, isPinned: isPinned,
                 nodeMode: nodeMode ?? false, complianceMode: complianceMode ?? false, payerMode: payerMode ?? false,
                 createdAt: createdAt, updatedAt: nil)
    }
}

struct MWMessage: Codable, Identifiable {
    let id: String
    let threadId: String
    let role: String
    let content: String
    let versionCreated: Int?
    let metadata: MWMessageMetadata?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, role, content, metadata
        case threadId = "thread_id"
        case versionCreated = "version_created"
        case createdAt = "created_at"
    }
}

// Flat response matching backend ThreadDetailResponse
struct MWThreadDetail: Codable {
    let id: String
    let title: String
    let taskType: MWTaskType?
    let status: String
    let version: Int
    let isPinned: Bool
    let nodeMode: Bool?
    let complianceMode: Bool?
    let payerMode: Bool?
    let createdAt: String
    let updatedAt: String
    let messages: [MWMessage]
    let currentState: [String: AnyCodable]

    var resolvedTaskType: MWTaskType {
        taskType ?? inferMWTaskType(from: currentState)
    }

    var thread: MWThread {
        MWThread(id: id, title: title, taskType: taskType, status: status,
                 version: version, isPinned: isPinned,
                 nodeMode: nodeMode ?? false, complianceMode: complianceMode ?? false, payerMode: payerMode ?? false,
                 createdAt: createdAt, updatedAt: updatedAt)
    }

    enum CodingKeys: String, CodingKey {
        case id, title, status, version, messages
        case taskType = "task_type"
        case isPinned = "is_pinned"
        case nodeMode = "node_mode"
        case complianceMode = "compliance_mode"
        case payerMode = "payer_mode"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case currentState = "current_state"
    }
}

struct MWSendMessageResponse: Codable {
    let userMessage: MWMessage
    let assistantMessage: MWMessage?
    let currentState: [String: AnyCodable]?
    let version: Int?
    let taskType: MWTaskType?
    let pdfUrl: String?
    let tokenUsage: MWTokenUsage?

    enum CodingKeys: String, CodingKey {
        case version
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
        case currentState = "current_state"
        case taskType = "task_type"
        case pdfUrl = "pdf_url"
        case tokenUsage = "token_usage"
    }
}

struct MWTokenUsage: Codable {
    let promptTokens: Int?
    let completionTokens: Int?
    let totalTokens: Int?
    let costDollars: Double?
    let model: String?
    let estimated: Bool?

    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case costDollars = "cost_dollars"
        case model, estimated
    }

    /// Formatted display string, e.g. "1.2k tok · $0.0012"
    var displayText: String? {
        let total = totalTokens ?? ((promptTokens ?? 0) + (completionTokens ?? 0))
        guard total > 0 else { return nil }
        let tokStr = total >= 1000 ? String(format: "%.1fk", Double(total) / 1000.0) : "\(total)"
        let prefix = (estimated == true) ? "~" : ""
        if let cost = costDollars, cost > 0 {
            return "\(prefix)\(tokStr) tok · $\(String(format: "%.4f", cost))"
        }
        return "\(prefix)\(tokStr) tok"
    }
}

struct MWDocumentVersion: Codable, Identifiable {
    var id: Int { version }
    let version: Int
    let diffSummary: String?
    let createdAt: String
    enum CodingKeys: String, CodingKey {
        case version
        case diffSummary = "diff_summary"
        case createdAt = "created_at"
    }
}

struct MWCreateThreadRequest: Codable {
    let title: String?
    let initialMessage: String?
    enum CodingKeys: String, CodingKey {
        case title
        case initialMessage = "initial_message"
    }
}


struct MWPinRequest: Codable {
    let pinned: Bool
}

struct MWRevertRequest: Codable {
    let version: Int
}

struct MWFinalizeResponse: Codable {
    let threadId: String
    let status: String
    let version: Int
    let pdfUrl: String?
    let linkedOfferLetterId: String?

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case status, version
        case pdfUrl = "pdf_url"
        case linkedOfferLetterId = "linked_offer_letter_id"
    }
}

// MARK: - Compliance Metadata Types

struct MWMessageMetadata: Codable {
    let complianceReasoning: [MWComplianceReasoningLocation]?
    let aiReasoningSteps: [MWAIReasoningStep]?
    let referencedCategories: [String]?
    let referencedLocations: [String]?
    let payerSources: [MWPayerPolicySource]?
    let affectedEmployees: [MWAffectedEmployeeGroup]?
    let complianceGaps: [MWComplianceGap]?
    let attachments: [MWMessageAttachment]?

    enum CodingKeys: String, CodingKey {
        case complianceReasoning = "compliance_reasoning"
        case aiReasoningSteps = "ai_reasoning_steps"
        case referencedCategories = "referenced_categories"
        case referencedLocations = "referenced_locations"
        case payerSources = "payer_sources"
        case affectedEmployees = "affected_employees"
        case complianceGaps = "compliance_gaps"
        case attachments
    }
}

struct MWMessageAttachment: Codable, Hashable {
    let url: String
    let kind: String?
    var filename: String?
    var contentType: String?
    var size: Int?

    enum CodingKeys: String, CodingKey {
        case url, kind, filename, size
        case contentType = "content_type"
    }

    init(url: String, kind: String? = nil, filename: String? = nil,
         contentType: String? = nil, size: Int? = nil) {
        self.url = url
        self.kind = kind
        self.filename = filename
        self.contentType = contentType
        self.size = size
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.url = try c.decode(String.self, forKey: .url)
        self.kind = try c.decodeIfPresent(String.self, forKey: .kind)
        self.filename = try c.decodeIfPresent(String.self, forKey: .filename)
        self.contentType = try c.decodeIfPresent(String.self, forKey: .contentType)
        self.size = try c.decodeIfPresent(Int.self, forKey: .size)
    }

    var isImage: Bool {
        if kind == "image" { return true }
        if let ct = contentType, ct.lowercased().hasPrefix("image/") { return true }
        return false
    }
}

struct MWComplianceReasoningLocation: Codable {
    let locationId: String
    let locationLabel: String
    let facilityAttributes: [String: AnyCodable]?
    let activatedProfiles: [MWActivatedProfile]
    let categories: [MWComplianceReasoningCategory]

    enum CodingKeys: String, CodingKey {
        case locationId = "location_id"
        case locationLabel = "location_label"
        case facilityAttributes = "facility_attributes"
        case activatedProfiles = "activated_profiles"
        case categories
    }
}

struct MWActivatedProfile: Codable {
    let label: String
    let categories: [String]
}

struct MWComplianceReasoningCategory: Codable {
    let category: String
    let governingLevel: String?
    let precedenceType: String?
    let reasoningText: String?
    let legalCitation: String?
    let allLevels: [MWComplianceReasoningLevel]

    enum CodingKeys: String, CodingKey {
        case category
        case governingLevel = "governing_level"
        case precedenceType = "precedence_type"
        case reasoningText = "reasoning_text"
        case legalCitation = "legal_citation"
        case allLevels = "all_levels"
    }
}

struct MWComplianceReasoningLevel: Codable {
    let jurisdictionLevel: String
    let jurisdictionName: String
    let title: String?
    let currentValue: String?
    let numericValue: Double?
    let sourceUrl: String?
    let statuteCitation: String?
    let isGoverning: Bool
    let effectiveDate: String?
    let lastVerifiedAt: String?
    let previousValue: String?
    let lastChangedAt: String?
    let expirationDate: String?
    let requiresWrittenPolicy: Bool?
    let penaltySummary: String?
    let enforcingAgency: String?

    enum CodingKeys: String, CodingKey {
        case jurisdictionLevel = "jurisdiction_level"
        case jurisdictionName = "jurisdiction_name"
        case title
        case currentValue = "current_value"
        case numericValue = "numeric_value"
        case sourceUrl = "source_url"
        case statuteCitation = "statute_citation"
        case isGoverning = "is_governing"
        case effectiveDate = "effective_date"
        case lastVerifiedAt = "last_verified_at"
        case previousValue = "previous_value"
        case lastChangedAt = "last_changed_at"
        case expirationDate = "expiration_date"
        case requiresWrittenPolicy = "requires_written_policy"
        case penaltySummary = "penalty_summary"
        case enforcingAgency = "enforcing_agency"
    }
}

struct MWAIReasoningStep: Codable {
    let step: Int
    let question: String
    let answer: String
    let conclusion: String
    let sources: [String]?
}

struct MWAffectedEmployeeGroup: Codable {
    let location: String
    let count: Int
    let matchType: String?

    enum CodingKeys: String, CodingKey {
        case location, count
        case matchType = "match_type"
    }
}

struct MWComplianceGap: Codable {
    let category: String
    let label: String
    let status: String
}

struct MWPayerPolicySource: Codable {
    let payerName: String
    let policyTitle: String?
    let policyNumber: String?
    let sourceUrl: String?
    let similarity: Double?

    enum CodingKeys: String, CodingKey {
        case payerName = "payer_name"
        case policyTitle = "policy_title"
        case policyNumber = "policy_number"
        case sourceUrl = "source_url"
        case similarity
    }
}

// MARK: - Mode Toggle Request Types

struct MWNodeModeRequest: Codable {
    let nodeMode: Bool
    enum CodingKeys: String, CodingKey { case nodeMode = "node_mode" }
}

struct MWComplianceModeRequest: Codable {
    let complianceMode: Bool
    enum CodingKeys: String, CodingKey { case complianceMode = "compliance_mode" }
}

struct MWPayerModeRequest: Codable {
    let payerMode: Bool
    enum CodingKeys: String, CodingKey { case payerMode = "payer_mode" }
}

struct MWUpdateTitleRequest: Codable {
    let title: String
}
