import Foundation
import Observation

@MainActor
@Observable
final class MarketplaceViewModel: LoadableVM {
    var listings: [Listing] = []
    var city: String?
    var isLoading = false
    var error: String?
    let redeemFlow = RedeemFlowModel()

    func load() async {
        await withLoad {
            listings = try await RewardsService.shared.marketplace(city: city)
        }
    }
}
