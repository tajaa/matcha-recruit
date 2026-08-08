import Foundation
import Observation

@MainActor
@Observable
final class BoardsListViewModel: LoadableVM {
    var memberships: [BoardMembership] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            memberships = try await BoardService.shared.memberships()
        }
    }

    func cancel(_ id: String) async {
        await withLoad {
            try await BoardService.shared.cancelMembership(id: id)
            memberships.removeAll { $0.id == id }
        }
    }
}
