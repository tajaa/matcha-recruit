import Foundation
import Observation

@MainActor
@Observable
final class CampaignsViewModel: LoadableVM {
    var campaigns: [PromoCampaign] = []
    var stores: [Store] = []
    var isLoading = false
    var isCreating = false
    var error: String?

    func load() async {
        await withLoad {
            async let loadedCampaigns = PromoService.shared.campaigns()
            async let loadedStores = BrandAdminService.shared.stores()
            campaigns = try await loadedCampaigns
            stores = try await loadedStores
        }
    }

    func create(_ body: PromoCampaignCreate) async -> PromoCampaign? {
        isCreating = true
        defer { isCreating = false }
        do {
            let created = try await PromoService.shared.createCampaign(body)
            campaigns.insert(created, at: 0)
            error = nil
            return created
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
            return nil
        }
    }

    func push(_ campaign: PromoCampaign) async {
        do {
            let result = try await PromoService.shared.pushCampaign(id: campaign.id)
            await load()
            // A zero-recipient push leaves push_sent_at unset server-side so the
            // button reappears — surface that explicitly, it isn't a failure.
            error = result.pushed ? nil : "No followers were near \(campaign.store_name ?? "the store") just now — try again later."
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }
}
