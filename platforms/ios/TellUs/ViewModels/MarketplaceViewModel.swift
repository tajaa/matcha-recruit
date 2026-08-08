import Foundation
import Observation

@MainActor
@Observable
final class MarketplaceViewModel {
    var listings: [Listing] = []
    var city: String?
    var isLoading = false
    var error: String?
    let redeemFlow = RedeemFlowModel()

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            listings = try await RewardsService.shared.marketplace(city: city)
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    /// Maps the server's 409 detail text to user-facing copy. Extracted as
    /// a static func for unit testing (Tests/RedeemErrorMappingTests.swift).
    static func redeemMessage(from detail: String) -> String {
        let d = detail.lowercased()
        if d.contains("point") || d.contains("insufficient") {
            return "Not enough points for this reward."
        }
        if d.contains("sold") || d.contains("quantity") {
            return "This reward is sold out."
        }
        if d.contains("board") || d.contains("member") {
            return "Members-only reward — join the brand's board first."
        }
        return detail
    }
}
