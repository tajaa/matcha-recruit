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

    // Degrade an unknown/future plan string to `.free` rather than throwing —
    // a raw-value enum would otherwise fail the entire entitlements decode and
    // leave the client unable to read the tier at all.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MWPlan(rawValue: raw) ?? .free
    }

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

    func has(_ feature: String) -> Bool { features[feature] == true }
}

struct MWEntitlementQuotas: Codable {
    let tokenLimit: Int?
    let windowHours: Int?
    let used: Int?
    let remaining: Int?
    let resetsAt: String?

    enum CodingKeys: String, CodingKey {
        case tokenLimit = "token_limit"
        case windowHours = "window_hours"
        case used, remaining
        case resetsAt = "resets_at"
    }
}
