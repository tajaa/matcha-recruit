import Foundation
import Observation

@MainActor
@Observable
final class AppState {
    enum Phase: Equatable {
        case restoring
        case loggedOut
        case verifyPending(email: String)
        case owner
        case creator
    }

    var phase: Phase = .restoring
    var account: CappeAccount?
    /// Set by AuthViewModel right before transitioning to `.verifyPending` so
    /// VerifyWaitView's "I've confirmed — sign me in" can retry without the
    /// user re-entering credentials. Session-scoped (memory-only, never
    /// persisted) — a cold relaunch into `.verifyPending` finds this nil and
    /// the view falls back to asking for manual re-login.
    var pendingCredentials: (email: String, password: String)?

    /// Owner's site list + current selection. `siteId` is passed per call to
    /// domain services (never stored there — plan §4), so this is the ONE
    /// place a site switch can race; every mutation goes through
    /// `selectSite`/`addSite`/`updateSite` below.
    var sites: [CappeSite] = []
    var activeSite: CappeSite?
    var sitesLoading = false
    var sitesError: String?
    /// True only after a load has actually completed. RootView gates the
    /// blocking first-site screen on this, so "not started yet" and
    /// "cancelled" are never misread as "this account genuinely has no sites".
    private(set) var sitesLoaded = false

    /// Bumped on every session boundary (login/route, logout). `loadSites`
    /// captures it and drops any write whose epoch is stale — cancellation
    /// alone isn't enough, a response that already resumed its continuation
    /// would still land.
    private var sessionEpoch = 0
    private var sitesTask: Task<Void, Never>?

    private static let lastSiteIdKey = "cappe.lastSiteId"

    init() {
        // Fired by APIClient only after a DEFINITIVE refresh rejection
        // (401/403), never on network blips or decode errors. There is no
        // onPaymentRequired wall — see APIClient's doc comment.
        APIClient.shared.onUnauthorized = { [weak self] in
            Task { @MainActor in self?.didLogout(serverSide: false) }
        }
        Task { await restore() }
    }

    func restore() async {
        if let account = await AuthService.shared.restoreSession() {
            route(account)
        } else {
            phase = .loggedOut
        }
    }

    /// `account_type` is single-valued and fixed at signup — never both
    /// owner+creator (server/app/cappe/models/auth.py:17; routes/creators.py:43
    /// 403s non-creators).
    func route(_ account: CappeAccount) {
        self.account = account
        pendingCredentials = nil
        phase = account.account_type == .creator ? .creator : .owner
        sitesTask?.cancel()
        sessionEpoch += 1
        sitesLoaded = false
        sitesError = nil
        if phase == .owner {
            sitesLoading = true  // set SYNCHRONOUSLY — the Task below runs later
            sitesTask = Task { await loadSites() }
        } else {
            sitesLoading = false
        }
    }

    /// Fetches the owner's sites and resolves `activeSite`: keep the current
    /// selection if it still exists, else restore the last-used site id, else
    /// fall back to the newest site (server returns `ORDER BY created_at
    /// DESC` — sites.py:112).
    func loadSites() async {
        let epoch = sessionEpoch
        sitesLoading = true
        defer { if epoch == sessionEpoch { sitesLoading = false } }
        do {
            let fetched = try await SitesService.shared.list()
            guard epoch == sessionEpoch else { return }
            sites = fetched
            sitesError = nil
            sitesLoaded = true
            if let current = activeSite, let match = sites.first(where: { $0.id == current.id }) {
                activeSite = match
            } else {
                let lastId = UserDefaults.standard.string(forKey: Self.lastSiteIdKey)
                activeSite = sites.first(where: { $0.id == lastId }) ?? sites.first
            }
        } catch {
            guard epoch == sessionEpoch, !error.isCancellation else { return }
            sitesError = error.localizedDescription
        }
    }

    func selectSite(_ site: CappeSite) {
        activeSite = site
        UserDefaults.standard.set(site.id, forKey: Self.lastSiteIdKey)
    }

    /// Called after `SitesService.create` — the new site becomes active
    /// immediately (matches web's post-create redirect into the new site).
    func addSite(_ site: CappeSite) {
        sites.insert(site, at: 0)
        selectSite(site)
    }

    /// Called after a mutation that returns the updated row (e.g. publish) so
    /// every view reading `sites`/`activeSite` sees the change without a
    /// full `loadSites()` round-trip.
    func updateSite(_ site: CappeSite) {
        if let idx = sites.firstIndex(where: { $0.id == site.id }) { sites[idx] = site }
        if activeSite?.id == site.id { activeSite = site }
    }

    func didLogin(_ response: CappeTokenResponse) {
        route(response.account)
    }

    /// Idempotent — a background 401 firing `onUnauthorized` and a manual
    /// logout tap can both land here without double side effects. Both
    /// branches clear the keychain: `serverSide` is a real user-initiated
    /// logout (best-effort server notify, see AuthService.logout); the other
    /// is a DEFINITIVE refresh rejection (`_isAuthRejection` in APIClient) —
    /// the stored refresh token is dead either way and must not survive to
    /// the next cold launch.
    func didLogout(serverSide: Bool = true) {
        guard phase != .loggedOut else { return }
        if serverSide {
            AuthService.shared.logout()
        } else {
            AuthService.shared.clearLocalSession()
        }
        sitesTask?.cancel()
        sitesTask = nil
        sessionEpoch += 1
        account = nil
        pendingCredentials = nil
        sites = []
        activeSite = nil
        sitesError = nil
        sitesLoaded = false
        sitesLoading = false
        phase = .loggedOut
        URLCache.shared.removeAllCachedResponses()
    }
}
