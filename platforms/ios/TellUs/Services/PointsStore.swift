import Foundation
import Observation

/// Single source of truth for the consumer's points balance, so a redeem on
/// the Marketplace or a Board deal both immediately reflect on Home instead
/// of leaving it stale until the next RewardsHomeViewModel.load().
@MainActor
@Observable
final class PointsStore {
    static let shared = PointsStore()
    var balance: PointsBalance?
    private init() {}

    func refresh() async {
        balance = (try? await RewardsService.shared.balance()) ?? balance
    }
}
