import Foundation
import Observation

@MainActor
@Observable
final class CatalogListViewModel: LoadableVM {
    var products: [CappeProduct] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.products = try await CatalogService.shared.list(siteId: siteId)
        }
    }

    func delete(siteId: String, productId: String) async {
        do {
            try await CatalogService.shared.delete(siteId: siteId, productId: productId)
            products.removeAll { $0.id == productId }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
