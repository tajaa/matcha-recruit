import Foundation
import Observation

@MainActor
@Observable
final class OrdersListViewModel: LoadableVM {
    var orders: [CappeOrder] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.orders = try await OrdersService.shared.list(siteId: siteId)
        }
    }
}
