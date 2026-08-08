import Foundation
import Observation

@MainActor
@Observable
final class BoardsListViewModel {
    var memberships: [BoardMembership] = []
    var isLoading = false
    var error: String?

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            memberships = try await BoardService.shared.memberships()
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func cancel(_ id: String) async {
        error = nil
        do {
            try await BoardService.shared.cancelMembership(id: id)
            memberships.removeAll { $0.id == id }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
