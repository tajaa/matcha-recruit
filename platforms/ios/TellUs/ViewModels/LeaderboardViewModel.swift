import Foundation
import Observation

@MainActor
@Observable
final class LeaderboardViewModel: LoadableVM {
    var entries: [LeaderboardEntry] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            entries = try await GamificationService.shared.leaderboard()
        }
    }
}
