import Foundation

/// Brand-side feedback triage. All calls require an active brand plan
/// (402 on lapse) — see BillingWallView / AppState.handle402.
final class FeedbackService {
    static let shared = FeedbackService()
    private let client = APIClient.shared
    private init() {}

    func list(storeId: String? = nil, status: ReportStatus? = nil, sentiment: Sentiment? = nil,
              limit: Int = 25, offset: Int = 0) async throws -> [Report] {
        var components = URLComponents()
        var items = [URLQueryItem(name: "limit", value: String(limit)), URLQueryItem(name: "offset", value: String(offset))]
        if let storeId { items.append(URLQueryItem(name: "store_id", value: storeId)) }
        if let status { items.append(URLQueryItem(name: "status", value: status.rawValue)) }
        if let sentiment { items.append(URLQueryItem(name: "sentiment", value: sentiment.rawValue)) }
        components.queryItems = items
        let query = components.percentEncodedQuery.map { "?" + $0 } ?? ""
        return try await client.request(method: "GET", path: "/feedback" + query)
    }

    func stats() async throws -> FeedbackStats {
        try await client.request(method: "GET", path: "/feedback/stats")
    }

    /// Media URLs on the returned Report are freshly presigned here.
    func detail(id: String) async throws -> Report {
        try await client.request(method: "GET", path: "/feedback/\(id)")
    }

    func setStatus(id: String, _ status: ReportStatus) async throws {
        try await client.requestVoid(method: "PATCH", path: "/feedback/\(id)/status", body: StatusPatch(status: status.rawValue))
    }

    func decideReward(id: String, approve: Bool) async throws {
        try await client.requestVoid(method: "POST", path: "/feedback/\(id)/reward", body: RewardDecision(approve: approve))
    }

    func heart(id: String) async throws {
        try await client.requestVoid(method: "POST", path: "/feedback/\(id)/heart")
    }

    func unheart(id: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/feedback/\(id)/heart")
    }

    /// Public reply shown on /b/{slug}, ≤2000 chars.
    func setReply(id: String, body: String) async throws {
        try await client.requestVoid(method: "PUT", path: "/feedback/\(id)/reply", body: ReplyPut(body: body))
    }

    func deleteReply(id: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/feedback/\(id)/reply")
    }

    /// publish_at only ever moves EARLIER — irreversible, confirm in UI.
    func publishNow(id: String) async throws {
        try await client.requestVoid(method: "POST", path: "/feedback/\(id)/publish-now")
    }
}
