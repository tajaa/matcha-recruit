import Foundation
import Observation

@MainActor
@Observable
final class HomeViewModel: LoadableVM {
    var readiness: CappeReadiness?
    var isLoading = false
    var error: String?

    var isPublishing = false
    /// Set only on a `publishBlocked` 422 — HomeView highlights rows whose
    /// `key` is in this set instead of (or alongside) the generic `error`
    /// banner. Keys, not labels — display copy is free to change.
    var publishBlockedKeys: Set<String>?

    func loadReadiness(siteId: String) async {
        await withLoad {
            self.readiness = try await SitesService.shared.readiness(siteId: siteId)
        }
    }

    /// Called on a site switch so the new site starts from a clean slate —
    /// otherwise the previous site's checklist and blocked-key highlighting
    /// would stay on screen until the new readiness fetch resolves.
    func reset() {
        readiness = nil
        publishBlockedKeys = nil
        error = nil
    }

    /// Re-checks with the server rather than trusting a locally-computed
    /// "ready" flag — the checklist can go stale between load and tap.
    func publish(site: CappeSite, appState: AppState) async {
        isPublishing = true
        defer { isPublishing = false }
        error = nil
        publishBlockedKeys = nil
        do {
            let updated = try await SitesService.shared.publish(siteId: site.id)
            appState.updateSite(updated)
            await loadReadiness(siteId: site.id)
        } catch let APIError.publishBlocked(message, missing) {
            // Reload FIRST: withLoad clears `error` on entry, so assigning
            // the 422 message before this call would wipe it before the
            // banner ever renders. The blocked response carries no fresh
            // checklist, and the key highlighting below needs current `done`
            // flags, not the ones from the last successful load.
            await loadReadiness(siteId: site.id)
            self.error = message
            self.publishBlockedKeys = Set(missing)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
