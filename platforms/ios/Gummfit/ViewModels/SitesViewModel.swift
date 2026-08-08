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

    func create(appState: AppState) async {
        await withLoad {
            let site = try await SitesService.shared.create(name: self.name)
            appState.addSite(site)
        }
    }
}
