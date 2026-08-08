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
    /// 403s non-creators). Site loading + last-site restore land in Phase 1.
    func route(_ account: CappeAccount) {
        self.account = account
        phase = account.account_type == .creator ? .creator : .owner
    }

    func didLogin(_ response: CappeTokenResponse) {
        route(response.account)
    }

    /// Idempotent — a background 401 firing `onUnauthorized` and a manual
    /// logout tap can both land here without double side effects.
    func didLogout(serverSide: Bool = true) {
        guard phase != .loggedOut else { return }
        if serverSide {
            Task { await AuthService.shared.logout() }
        } else {
            APIClient.shared.accessToken = nil
        }
        account = nil
        phase = .loggedOut
        URLCache.shared.removeAllCachedResponses()
    }
}
