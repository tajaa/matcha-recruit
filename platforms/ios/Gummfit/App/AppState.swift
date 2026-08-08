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
        pendingCredentials = nil
        phase = account.account_type == .creator ? .creator : .owner
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
        account = nil
        pendingCredentials = nil
        phase = .loggedOut
        URLCache.shared.removeAllCachedResponses()
    }
}
