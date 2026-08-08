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
}
