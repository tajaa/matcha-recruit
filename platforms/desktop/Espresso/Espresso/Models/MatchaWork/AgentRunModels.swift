import Foundation

// Agent cards (`mw_tasks.category == "agent"`): the server's web agent answers
// the card with a structured result per review round.
// Backend: server/app/matcha/routes/matcha_work/agent_cards.py +
// services/matcha_work/agent_card/schema.py (`agent_result.v1`).

struct MWAgentLink: Decodable, Hashable {
    let retailer: String
    let url: String
    let price: Double?
}

struct MWAgentReview: Decodable, Hashable {
    let quote: String
    let sourceName: String
    let url: String
    let sentiment: String

    enum CodingKeys: String, CodingKey {
        case quote, url, sentiment
        case sourceName = "source_name"
    }
}

struct MWAgentImage: Decodable, Hashable {
    let url: String
    let pageUrl: String
    let alt: String

    enum CodingKeys: String, CodingKey {
        case url, alt
        case pageUrl = "page_url"
    }
}

struct MWAgentPrice: Decodable, Hashable {
    let amount: Double
    let currency: String
    let sourceUrl: String

    enum CodingKeys: String, CodingKey {
        case amount, currency
        case sourceUrl = "source_url"
    }
}

struct MWAgentRating: Decodable, Hashable {
    let value: Double
    let scale: Double
    let count: Int?
    let sourceUrl: String

    enum CodingKeys: String, CodingKey {
        case value, scale, count
        case sourceUrl = "source_url"
    }
}

struct MWAgentPick: Decodable, Hashable {
    let name: String
    let brand: String
    let why: [String]
    let price: MWAgentPrice?
    let rating: MWAgentRating?
    let reviews: [MWAgentReview]
    let images: [MWAgentImage]
    let buyLinks: [MWAgentLink]

    enum CodingKeys: String, CodingKey {
        case name, brand, why, price, rating, reviews, images
        case buyLinks = "buy_links"
    }
}

struct MWAgentCriterion: Decodable, Hashable {
    let name: String
    let why: String
}

struct MWAgentSection: Decodable, Hashable {
    let heading: String
    let bodyMd: String

    enum CodingKeys: String, CodingKey {
        case heading
        case bodyMd = "body_md"
    }
}

struct MWAgentSource: Decodable, Hashable {
    let title: String
    let url: String
}

struct MWAgentResult: Decodable, Hashable {
    let headline: String
    let summary: String
    let answerType: String
    let criteria: [MWAgentCriterion]
    let topPick: MWAgentPick?
    let alternatives: [MWAgentPick]
    let sections: [MWAgentSection]
    let caveats: [String]
    let sources: [MWAgentSource]
    let confidence: String
    let changesFromPrevious: String?

    enum CodingKeys: String, CodingKey {
        case headline, summary, criteria, alternatives, sections, caveats, sources, confidence
        case answerType = "answer_type"
        case topPick = "top_pick"
        case changesFromPrevious = "changes_from_previous"
    }
}

struct MWAgentRunStep: Decodable, Hashable {
    let seq: Int
    let kind: String
    let label: String
    let status: String
}

struct MWAgentRun: Decodable, Identifiable, Hashable {
    let id: String
    let round: Int
    let status: String
    let result: MWAgentResult?
    let error: String?
    let searchCalls: Int
    let steps: [MWAgentRunStep]

    enum CodingKeys: String, CodingKey {
        case id, round, status, result, error, steps
        case searchCalls = "search_calls"
    }

    var isLive: Bool { status == "queued" || status == "running" }
}

/// A purchase approved in the project chat ("want me to buy it?" → which
/// card). v1 is a handoff: nothing was charged; checkout happens at the link.
struct MWAgentPurchase: Decodable, Identifiable, Hashable {
    let id: String
    let itemName: String
    let retailer: String?
    let checkoutUrl: String
    let amount: Double?
    let currency: String?
    let cardLast4: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case id, retailer, amount, currency, status
        case itemName = "item_name"
        case checkoutUrl = "checkout_url"
        case cardLast4 = "card_last4"
    }
}

struct MWAgentRunsResponse: Decodable {
    let runs: [MWAgentRun]
    /// The caller's own purchase handoffs for this card. Optional so an older
    /// server without purchases still decodes.
    let purchases: [MWAgentPurchase]?
}

/// A saved card for agent purchases. Only brand, last 4, expiry and a label
/// ever come back from the server; the number is never returned.
struct MWPaymentCard: Decodable, Identifiable, Hashable {
    let id: String
    let label: String
    let brand: String
    let last4: String
    let expMonth: Int
    let expYear: Int

    enum CodingKeys: String, CodingKey {
        case id, label, brand, last4
        case expMonth = "exp_month"
        case expYear = "exp_year"
    }

    var brandName: String {
        switch brand {
        case "visa": return "Visa"
        case "mastercard": return "Mastercard"
        case "amex": return "Amex"
        case "discover": return "Discover"
        default: return "Card"
        }
    }
}

struct MWPaymentCardsState: Decodable {
    let enabled: Bool
    let configured: Bool
    let cards: [MWPaymentCard]
}

struct MWAgentRunQueued: Decodable {
    let runId: String
    let round: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case round, status
        case runId = "run_id"
    }
}

extension MatchaWorkService {
    /// Every agent pass on the card, newest first, plus your purchase handoffs.
    func agentRuns(projectId: String, taskId: String) async throws -> MWAgentRunsResponse {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/agent-runs"
        )
    }

    // Saved payment cards (server: routes/matcha_work/payment_cards.py). The
    // number is sent once and encrypted server-side; there is no CVV field.

    func paymentCards() async throws -> MWPaymentCardsState {
        try await client.request(method: "GET", path: "\(basePath)/payment-cards")
    }

    func addPaymentCard(number: String, expMonth: Int, expYear: Int, label: String) async throws -> MWPaymentCard {
        struct Body: Encodable {
            let number: String
            let exp_month: Int
            let exp_year: Int
            let label: String
        }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/payment-cards",
            body: Body(number: number, exp_month: expMonth, exp_year: expYear, label: label)
        )
    }

    func deletePaymentCard(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/payment-cards/\(id)")
    }

    /// "Run again" after a failed pass (or a manual move back to To do).
    func rerunAgent(projectId: String, taskId: String) async throws -> MWAgentRunQueued {
        struct Empty: Encodable {}
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/agent-runs",
            body: Empty()
        )
    }
}

extension APIError {
    /// The server's `detail` (a string, or an object's `message`) as one line.
    var serverDetail: String? {
        guard case let .httpError(_, message) = self,
              let data = message.data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let detail = response["detail"] as? String { return detail }
        return (response["detail"] as? [String: Any])?["message"] as? String
    }

    /// The monthly agent-run cap (429 `agent_run_limit`) as one readable line.
    var agentRunLimitMessage: String? {
        guard case let .httpError(code, message) = self, code == 429,
              let data = message.data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = response["detail"] as? [String: Any],
              detail["code"] as? String == "agent_run_limit" else {
            return nil
        }
        let limit = detail["limit"] as? Int ?? 0
        return "You've used all \(limit) agent runs this month."
    }
}
