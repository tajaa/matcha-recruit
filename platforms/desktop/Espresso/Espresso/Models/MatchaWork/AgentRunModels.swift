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

struct MWAgentRunsResponse: Decodable {
    let runs: [MWAgentRun]
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
    /// Every agent pass on the card, newest first.
    func agentRuns(projectId: String, taskId: String) async throws -> [MWAgentRun] {
        let res: MWAgentRunsResponse = try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/agent-runs"
        )
        return res.runs
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
