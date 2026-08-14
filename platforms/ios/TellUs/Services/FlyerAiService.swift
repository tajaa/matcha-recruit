import Foundation

final class FlyerAiService {
    static let shared = FlyerAiService()
    private let client = APIClient.shared
    private init() {}

    func assist(campaignID: String, request: FlyerAssistRequest) async throws -> FlyerAssistResponse {
        try await client.request(
            method: "POST",
            path: "/promo/campaigns/\(campaignID)/design/assist",
            body: request
        )
    }

    func ideas(campaignID: String) async throws -> FlyerIdeasResponse {
        try await client.request(
            method: "POST",
            path: "/promo/campaigns/\(campaignID)/design/ideas",
            body: EmptyBody()
        )
    }

    func schema() async throws -> FlyerAiSchema {
        try await client.request(method: "GET", path: "/promo/design/schema")
    }
}

private struct EmptyBody: Encodable {}
