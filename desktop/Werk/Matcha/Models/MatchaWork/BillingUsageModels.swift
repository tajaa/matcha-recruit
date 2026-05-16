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
