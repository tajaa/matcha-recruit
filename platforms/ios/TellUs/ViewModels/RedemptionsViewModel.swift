import Foundation
import Observation

@MainActor
@Observable
final class RedemptionsViewModel {
    var redemptions: [Redemption] = []
    var isLoading = false
    var error: String?

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            redemptions = try await RewardsService.shared.redemptions()
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
