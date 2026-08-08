import Foundation
import Observation

/// Shared redeem-confirm state, used by both the Marketplace and Board-deal
/// redeem flows so RedeemConfirmSheet is a single reusable component instead
/// of the Marketplace-only sheet + a separate fire-and-forget board path.
@MainActor
@Observable
final class RedeemFlowModel {
    var lastRedemption: Redemption?
    var error: String?
    var isRedeeming = false

    /// Call when presenting the sheet for a (possibly different) listing —
    /// clears any success/error state left over from the previous listing.
    func begin() {
        lastRedemption = nil
        error = nil
    }

    func redeem(_ listing: Listing) async {
        isRedeeming = true; defer { isRedeeming = false }
        error = nil
        do {
            lastRedemption = try await RewardsService.shared.redeem(listingId: listing.id)
            await PointsStore.shared.refresh()
        } catch let APIError.httpError(409, detail) {
            error = RedeemErrorMapping.message(from: detail)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
