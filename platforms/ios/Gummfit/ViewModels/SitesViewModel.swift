import Foundation
import Observation

/// Backs CreateSiteView. List/switch live directly on AppState (plan §5) —
/// this VM is only for the one mutating action (create).
@MainActor
@Observable
final class SitesViewModel: LoadableVM {
    var name = ""
    var isLoading = false
    var error: String?

    var canSubmit: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isLoading
    }

    @discardableResult
    func create(appState: AppState) async -> Bool {
        var created = false
        await withLoad {
            let trimmed = self.name.trimmingCharacters(in: .whitespacesAndNewlines)
            let site = try await SitesService.shared.create(name: trimmed)
            appState.addSite(site)
            created = true
        }
        return created
    }
}
