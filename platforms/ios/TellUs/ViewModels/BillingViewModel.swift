import Foundation
import Observation

@MainActor
@Observable
final class BillingViewModel: LoadableVM {
    var status: BillingStatus?
    var pricing: BrandPricing?
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            async let s = BillingService.shared.status()
            async let p = BillingService.shared.pricing()
            status = try await s
            pricing = try await p
        }
    }

    func setLocations(_ count: Int) async {
        await withLoad {
            status = try await BillingService.shared.setLocations(count: count)
        }
    }
}
