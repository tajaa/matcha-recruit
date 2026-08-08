import Foundation
import Observation

@MainActor
@Observable
final class HomeViewModel: LoadableVM {
    var readiness: CappeReadiness?
    var isLoading = false
    var error: String?

    var isPublishing = false
    /// Set only on a `publishBlocked` 422 — HomeView highlights these labels
    /// in the checklist instead of (or alongside) the generic `error` banner.
    var publishBlockedLabels: [String]?

    func loadReadiness(siteId: String) async {
        await withLoad {
            self.readiness = try await SitesService.shared.readiness(siteId: siteId)
        }
    }

    /// Re-checks with the server rather than trusting a locally-computed
    /// "ready" flag — the checklist can go stale between load and tap.
    func publish(site: CappeSite, appState: AppState) async {
        isPublishing = true
        defer { isPublishing = false }
        error = nil
        publishBlockedLabels = nil
        do {
            let updated = try await SitesService.shared.publish(siteId: site.id)
            appState.updateSite(updated)
            await loadReadiness(siteId: site.id)
        } catch let APIError.publishBlocked(message, missing) {
            self.error = message
            self.publishBlockedLabels = missing
            // The blocked response doesn't include a fresh checklist, so
            // pull one — the label highlighting above needs current `done`
            // flags, not the ones from the last successful load.
            await loadReadiness(siteId: site.id)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
