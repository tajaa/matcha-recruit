import Foundation

private let mwISO8601WithFractionalSeconds: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
}()

private let mwISO8601DateFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter
}()

func parseMWDate(_ iso: String) -> Date? {
    mwISO8601WithFractionalSeconds.date(from: iso) ?? mwISO8601DateFormatter.date(from: iso)
}

enum MWTaskType: String, Codable {
    case offerLetter = "offer_letter"
    case review
    case workbook
    case onboarding
    case presentation
    case handbook
    case resumeBatch = "resume_batch"
    case inventory
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
        }
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

    enum CodingKeys: String, CodingKey {
        case complianceReasoning = "compliance_reasoning"
        case aiReasoningSteps = "ai_reasoning_steps"
        case referencedCategories = "referenced_categories"
        case referencedLocations = "referenced_locations"
        case payerSources = "payer_sources"
        case affectedEmployees = "affected_employees"
        case complianceGaps = "compliance_gaps"
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

// MARK: - Usage Summary

struct MWUsageSummary: Codable {
    let periodDays: Int
    let generatedAt: String
    let totals: MWUsageTotals
    let byModel: [MWModelUsage]

    enum CodingKeys: String, CodingKey {
        case periodDays = "period_days"
        case generatedAt = "generated_at"
        case totals
        case byModel = "by_model"
    }
}

struct MWUsageTotals: Codable {
    let promptTokens: Int
    let completionTokens: Int
    let totalTokens: Int
    let operationCount: Int
    let estimatedOperations: Int?

    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case operationCount = "operation_count"
        case estimatedOperations = "estimated_operations"
    }
}

struct MWModelUsage: Codable, Identifiable {
    var id: String { model }
    let model: String
    let promptTokens: Int
    let completionTokens: Int
    let totalTokens: Int
    let operationCount: Int
    let costDollars: Double?

    enum CodingKeys: String, CodingKey {
        case model
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case operationCount = "operation_count"
        case costDollars = "cost_dollars"
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

// MARK: - Projects

enum MWProjectType: String, Codable {
    case general
    case presentation
    case recruiting
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
    var collaborators: [MWProjectCollaborator]?
    let createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, version, sections
        case projectType = "project_type"
        case isPinned = "is_pinned"
        case projectData = "project_data"
        case chatCount = "chat_count"
        case collaborators
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct MWProjectSection: Codable, Identifiable {
    let id: String
    var title: String
    var content: String?
    var sourceMessageId: String?

    enum CodingKeys: String, CodingKey {
        case id, title, content
        case sourceMessageId = "source_message_id"
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

// MARK: - Inbox

struct MWInboxConversation: Codable, Identifiable {
    let id: String
    var title: String?
    let isGroup: Bool?
    var lastMessageAt: String?
    var lastMessagePreview: String?
    var participants: [MWInboxParticipant]?
    var unreadCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, participants
        case isGroup = "is_group"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case unreadCount = "unread_count"
    }
}

struct MWInboxConversationDetail: Codable, Identifiable {
    let id: String
    var title: String?
    let isGroup: Bool?
    let createdBy: String?
    var lastMessageAt: String?
    var lastMessagePreview: String?
    var participants: [MWInboxParticipant]?
    var messages: [MWInboxMessage]?
    var unreadCount: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, participants, messages
        case isGroup = "is_group"
        case createdBy = "created_by"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case unreadCount = "unread_count"
        case createdAt = "created_at"
    }
}

struct MWInboxMessage: Codable, Identifiable {
    let id: String
    let conversationId: String
    let senderId: String
    let senderName: String
    let content: String
    let attachments: [MWInboxAttachment]?
    let createdAt: String
    let editedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, content, attachments
        case conversationId = "conversation_id"
        case senderId = "sender_id"
        case senderName = "sender_name"
        case createdAt = "created_at"
        case editedAt = "edited_at"
    }
}

struct MWInboxAttachment: Codable, Identifiable {
    var id: String { url }
    let url: String
    let filename: String
    let contentType: String
    let size: Int

    enum CodingKeys: String, CodingKey {
        case url, filename, size
        case contentType = "content_type"
    }

    var isImage: Bool { contentType.hasPrefix("image/") }
}

struct MWInboxParticipant: Codable, Identifiable {
    var id: String { userId }
    let userId: String
    let name: String
    let email: String
    let role: String?
    let avatarUrl: String?
    let lastReadAt: String?
    let isMuted: Bool?

    enum CodingKeys: String, CodingKey {
        case name, email, role
        case userId = "user_id"
        case avatarUrl = "avatar_url"
        case lastReadAt = "last_read_at"
        case isMuted = "is_muted"
    }
}

struct MWInboxUserSearch: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let role: String?
    let avatarUrl: String?
    let companyName: String?

    enum CodingKeys: String, CodingKey {
        case id, email, name, role
        case avatarUrl = "avatar_url"
        case companyName = "company_name"
    }
}

// MARK: - Model Options

struct MWModelOption: Identifiable {
    let id: String
    let label: String
    let value: String
}

let mwModelOptions: [MWModelOption] = [
    MWModelOption(id: "flash-lite", label: "Flash Lite 3.1", value: "gemini-2.0-flash-lite"),
    MWModelOption(id: "flash", label: "Flash 3.0", value: "gemini-2.0-flash"),
    MWModelOption(id: "pro", label: "Pro 3.1", value: "gemini-2.5-pro-preview-05-06"),
]

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

// AnyCodable for flexible JSON
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Bool.self) { value = v }
        else if let v = try? container.decode(Int.self) { value = v }
        else if let v = try? container.decode(Double.self) { value = v }
        else if let v = try? container.decode(String.self) { value = v }
        else if let v = try? container.decode([String: AnyCodable].self) { value = v }
        else if let v = try? container.decode([AnyCodable].self) { value = v }
        else { value = NSNull() }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let v as Bool: try container.encode(v)
        case let v as Int: try container.encode(v)
        case let v as Double: try container.encode(v)
        case let v as String: try container.encode(v)
        case let v as [String: AnyCodable]: try container.encode(v)
        case let v as [AnyCodable]: try container.encode(v)
        default: try container.encodeNil()
        }
    }
}
