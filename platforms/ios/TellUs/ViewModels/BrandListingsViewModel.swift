import Foundation
import Observation

@MainActor
@Observable
final class BrandListingsViewModel: LoadableVM {
    var listings: [Listing] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            listings = try await BrandAdminService.shared.listings()
        }
    }

    func create(_ body: ListingCreate) async {
        await withLoad {
            let created = try await BrandAdminService.shared.createListing(body)
            listings.insert(created, at: 0)
        }
    }

    func update(id: String, _ body: ListingUpdate) async {
        await withLoad {
            let updated = try await BrandAdminService.shared.updateListing(id: id, body)
            if let idx = listings.firstIndex(where: { $0.id == id }) { listings[idx] = updated }
        }
    }

    func delete(id: String) async {
        await withLoad {
            try await BrandAdminService.shared.deleteListing(id: id)
            listings.removeAll { $0.id == id }
        }
    }

    func toggleActive(_ listing: Listing) async {
        await update(id: listing.id, ListingUpdate(
            title: nil, description: nil, image_url: nil, points_cost: nil, quantity_total: nil,
            redemption_type: nil, terms: nil, city: nil, state: nil, active_from: nil, active_to: nil,
            is_active: !listing.is_active, expiry_days: nil, visibility: nil
        ))
    }
}
