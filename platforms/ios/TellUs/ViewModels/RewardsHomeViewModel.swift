import Foundation
import Observation

@MainActor
@Observable
final class RewardsHomeViewModel: LoadableVM {
    var balance: PointsBalance?
    var badges: [BadgeItem] = []
    var recentLedger: [LedgerEntry] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            async let b = RewardsService.shared.balance()
            async let badgesResult = RewardsService.shared.badges()
            async let ledger = RewardsService.shared.ledger(limit: 8)
            balance = try await b
            PointsStore.shared.balance = balance
            badges = try await badgesResult
            recentLedger = try await ledger
        }
    }
}
