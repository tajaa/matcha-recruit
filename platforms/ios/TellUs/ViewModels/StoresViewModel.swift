import Foundation
import Observation

@MainActor
@Observable
final class StoresViewModel: LoadableVM {
    var stores: [Store] = []
    var links: [FeedbackLink] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            async let s = BrandAdminService.shared.stores()
            async let l = BrandAdminService.shared.links()
            stores = try await s
            links = try await l
        }
    }

    func createStore(_ body: StoreCreate) async {
        await withLoad {
            let store = try await BrandAdminService.shared.createStore(body)
            stores.append(store)
        }
    }

    func updateStore(id: String, _ body: StoreUpdate) async {
        await withLoad {
            let updated = try await BrandAdminService.shared.updateStore(id: id, body)
            if let idx = stores.firstIndex(where: { $0.id == id }) { stores[idx] = updated }
        }
    }

    func deleteStore(id: String) async {
        await withLoad {
            try await BrandAdminService.shared.deleteStore(id: id)
            stores.removeAll { $0.id == id }
        }
    }

    func createLink(_ body: LinkCreate) async {
        await withLoad {
            let link = try await BrandAdminService.shared.createLink(body)
            links.append(link)
        }
    }

    func revokeLink(id: String) async {
        await withLoad {
            let revoked = try await BrandAdminService.shared.revokeLink(id: id)
            if let idx = links.firstIndex(where: { $0.id == id }) { links[idx] = revoked }
        }
    }
}
