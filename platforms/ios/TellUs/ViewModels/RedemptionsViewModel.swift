import Foundation
import Observation

@MainActor
@Observable
final class RedemptionsViewModel: LoadableVM {
    var redemptions: [Redemption] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            redemptions = try await RewardsService.shared.redemptions()
        }
    }
}
