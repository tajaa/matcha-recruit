import Foundation
import Observation

@MainActor
@Observable
final class AppState {
    enum Phase: Equatable {
        case restoring
        case loggedOut
        case verifyPending(email: String)
        case consumer
        case brand
        /// Brand account whose plan_status != active — server 402s nearly
        /// everything except GET /brand, /billing/*, and board reads.
        case brandWall
    }

    var phase: Phase = .restoring
    var account: TellusAccount?
    /// Non-empty ⇒ this consumer moderates at least one brand's board
    /// (tellus_brand_members row) — drives the conditional Moderate tab.
    var moderatedBrands: [ModeratedBrand] = []
    var unreadCount = 0

    private var pollTask: Task<Void, Never>?

    init() {
        // Fired by APIClient only after a DEFINITIVE refresh rejection
        // (401/403), never on network blips or decode errors.
        APIClient.shared.onUnauthorized = { [weak self] in
            Task { @MainActor in self?.didLogout(serverSide: false) }
        }
        APIClient.shared.onPaymentRequired = { [weak self] in
            Task { @MainActor in self?.handle402() }
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

    func route(_ account: TellusAccount) {
        self.account = account
        if account.account_type == .brand {
            phase = account.plan_status == .active ? .brand : .brandWall
            moderatedBrands = []
        } else {
            phase = .consumer
            Task { [weak self] in
                self?.moderatedBrands = (try? await BoardManageService.shared.moderatedBrands()) ?? []
            }
        }
        startPolling()
    }

    func didLogin(_ response: TokenResponse) {
        route(response.account)
    }

    /// Idempotent — a background 401 firing `onUnauthorized` and a manual
    /// logout tap can both land here without double side effects.
    func didLogout(serverSide: Bool = true) {
        guard phase != .loggedOut else { return }
        pollTask?.cancel()
        pollTask = nil
        if serverSide {
            Task { await AuthService.shared.logout() }
        } else {
            APIClient.shared.accessToken = nil
        }
        account = nil
        moderatedBrands = []
        unreadCount = 0
        phase = .loggedOut
    }

    /// Runtime 402 on a brand-account call — route to the wall. Consumer
    /// moderators hitting a lapsed brand's /board/manage/* get a local alert
    /// instead (see BoardManageViewModel) since their OWN account is fine.
    func handle402() {
        guard account?.account_type == .brand else { return }
        phase = .brandWall
    }

    /// BillingWallView's Refresh button — re-fetches /auth/me and exits the
    /// wall if the plan is active again.
    func refreshWall() async {
        guard let refreshed = try? await AuthService.shared.fetchMe() else { return }
        route(refreshed)
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                if let items = try? await NotificationsService.shared.list(unreadOnly: true, limit: 100) {
                    self?.unreadCount = items.count
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    func pausePolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func resumePolling() {
        // Consistent with route()'s unconditional startPolling(): a walled
        // brand's own GET /notifications still works (require_tellus_account),
        // so don't stop polling for it on backgrounding just to silently
        // never resume.
        guard phase == .consumer || phase == .brand || phase == .brandWall else { return }
        startPolling()
    }
}
