import Foundation
import Observation

@MainActor
@Observable
final class RewardsHomeViewModel {
    var balance: PointsBalance?
    var badges: [BadgeItem] = []
    var recentLedger: [LedgerEntry] = []
    var isLoading = false
    var error: String?

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            async let b = RewardsService.shared.balance()
            async let badgesResult = RewardsService.shared.badges()
            async let ledger = RewardsService.shared.ledger(limit: 8)
            balance = try await b
            badges = try await badgesResult
            recentLedger = try await ledger
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
