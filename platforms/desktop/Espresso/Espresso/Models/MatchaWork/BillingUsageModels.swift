import Foundation

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

// MARK: - Billing

struct MWSubscription: Codable {
    let active: Bool
    let packId: String?
    let tokensPerCycle: Int?
    let amountCents: Int?
    let status: String?
    let currentPeriodEnd: String?

    var isPersonalPlus: Bool {
        active && packId == "matcha_work_personal"
    }

    enum CodingKeys: String, CodingKey {
        case active, status
        case packId = "pack_id"
        case tokensPerCycle = "tokens_per_cycle"
        case amountCents = "amount_cents"
        case currentPeriodEnd = "current_period_end"
    }
}

/// A personal plan's live price — set at /admin/pricing, the same number the
/// checkout charges. The paywall shows it instead of a built-in string.
struct MWPersonalPlanPrice: Codable {
    let plan: String
    let amountCents: Int

    /// "$20/mo", or "$9.50/mo" when the price has cents.
    var monthlyLabel: String {
        let dollars = amountCents / 100
        let cents = amountCents % 100
        return cents == 0 ? "$\(dollars)/mo" : String(format: "$%d.%02d/mo", dollars, cents)
    }

    enum CodingKeys: String, CodingKey {
        case plan
        case amountCents = "amount_cents"
    }
}

struct MWCheckoutResponse: Codable {
    let checkoutUrl: String
    let stripeSessionId: String?

    enum CodingKeys: String, CodingKey {
        case checkoutUrl = "checkout_url"
        case stripeSessionId = "stripe_session_id"
    }
}

// MARK: - Entitlements (Free / Lite / Pro / Business)

/// Werk plan ladder. Order matters — `>=` comparisons gate features
/// (business ranks with pro; business additionally unlocks the role-gated
/// Node/Compliance/Payer modes server-side).
enum MWPlan: String, Codable, Comparable {
    case free, lite, pro, business

    // NOTE: deliberately a strict raw-value decode — do NOT add an
    // unknown → .free fallback. AppState.refreshEntitlements' catch keeps
    // the LAST-KNOWN entitlements when the decode throws, so a subscriber
    // migrated to a future server-side tier keeps their paid gates until an
    // app update ships the new case. A .free fallback would decode
    // "successfully" and actively overwrite their paid plan with free.

    private var rank: Int {
        switch self {
        case .free: return 0
        case .lite: return 1
        case .pro, .business: return 2
        }
    }

    static func < (lhs: MWPlan, rhs: MWPlan) -> Bool { lhs.rank < rhs.rank }

    var displayName: String {
        switch self {
        case .free: return "Free"
        case .lite: return "Lite"
        case .pro: return "Pro"
        case .business: return "Business"
        }
    }
}

/// Server-resolved plan + feature map + rolling AI quota — the client's single
/// tier read (GET /matcha-work/entitlements). Replaces the old separate
/// isPlusActive / beta-flag reads.
struct MWEntitlements: Codable {
    let plan: MWPlan
    let features: [String: Bool]
    let quotas: MWEntitlementQuotas?
    /// What the workspace has switched on, as opposed to what the plan allows.
    let workspace: MWWorkspaceFlags?

    func has(_ feature: String) -> Bool { features[feature] == true }
}

struct MWWorkspaceFlags: Codable {
    let espressoAssistant: Bool?
    /// The chat model picker's rows and the row it starts on — the server's
    /// rule (`matcha_work_ai._models.picker_models`), not re-derived here.
    let chatModels: [MWChatModelRow]?
    let defaultChatModel: String?
    /// The assistant's model menu and where it starts (`agent_runtime.models`).
    /// Absent on servers that predate it, and when the assistant is off.
    var assistantModels: [MWAssistantModelRow]? = nil
    var defaultAssistantModel: String? = nil
    /// Job search (a personal account on a server with a listings provider).
    var jobSearch: Bool? = nil
    /// Espresso Tasks (switched on for this account: `agent_tasks.enqueue.tasks_enabled`).
    var agentTasks: Bool? = nil

    enum CodingKeys: String, CodingKey {
        case espressoAssistant = "espresso_assistant"
        case jobSearch = "job_search"
        case agentTasks = "agent_tasks"
        case chatModels = "chat_models"
        case defaultChatModel = "default_chat_model"
        case assistantModels = "assistant_models"
        case defaultAssistantModel = "default_assistant_model"
    }
}

/// One row of the assistant's model menu: the id the server runs and its name.
struct MWAssistantModelRow: Codable, Hashable {
    let id: String
    let label: String
}

/// The Espresso assistant's model menu for one person. The rows and where it
/// starts are the server's; the pick is remembered on this Mac
/// (`@AppStorage(storageKey)`) and sent with each message, and the server
/// re-checks it (`models.resolve`), so a stale pick just runs the default.
struct AssistantModelMenu {
    static let storageKey = "espresso-assistant-model"

    let rows: [MWAssistantModelRow]
    let defaultModel: String?

    init(workspace: MWWorkspaceFlags?) {
        rows = workspace?.assistantModels ?? []
        defaultModel = workspace?.defaultAssistantModel
    }

    /// Worth showing only when there is a choice to make.
    var hasChoice: Bool { rows.count > 1 }

    /// The row a stored pick runs on: the pick when offered, else the default.
    func current(_ pick: String) -> MWAssistantModelRow? {
        rows.first { $0.id == pick } ?? rows.first { $0.id == defaultModel }
    }

    /// What a message carries: the pick when offered, else nil (the default).
    func value(for pick: String) -> String? {
        rows.contains { $0.id == pick } ? pick : nil
    }
}

/// One picker row from the server: a model id, and whether this plan has it
/// (a locked row shows with a lock and opens the paywall).
struct MWChatModelRow: Codable, Hashable {
    let id: String
    let locked: Bool
}

/// A counted allowance (agent-card runs this month, assistant requests today).
struct MWRunQuota: Codable, Hashable {
    let limit: Int
    let used: Int
    let remaining: Int
    let resetsAt: String?

    enum CodingKeys: String, CodingKey {
        case limit, used, remaining
        case resetsAt = "resets_at"
    }
}

struct MWEntitlementQuotas: Codable {
    let tokenLimit: Int?
    let windowHours: Int?
    let used: Int?
    let remaining: Int?
    let resetsAt: String?
    /// Agent-card runs this UTC month.
    let agentRuns: MWRunQuota?
    /// Espresso assistant requests this UTC day.
    let assistantRuns: MWRunQuota?
    /// Job searches this UTC month.
    var jobSearches: MWRunQuota? = nil

    enum CodingKeys: String, CodingKey {
        case tokenLimit = "token_limit"
        case windowHours = "window_hours"
        case used, remaining
        case resetsAt = "resets_at"
        case agentRuns = "agent_runs"
        case assistantRuns = "assistant_runs"
        case jobSearches = "job_searches"
    }
}
