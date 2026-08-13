import Foundation
import Observation

@MainActor
@Observable
final class CampaignsViewModel: LoadableVM {
    var campaigns: [PromoCampaign] = []
    var isLoading = false
    var isCreating = false
    var error: String?

    func load() async {
        await withLoad {
            campaigns = try await PromoService.shared.campaigns()
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
}
