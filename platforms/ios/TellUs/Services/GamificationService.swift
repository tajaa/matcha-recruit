import Foundation

final class GamificationService {
    static let shared = GamificationService()
    private let client = APIClient.shared
    private init() {}

    func leaderboard() async throws -> [LeaderboardEntry] {
        try await client.request(method: "GET", path: "/leaderboard")
    }
}
