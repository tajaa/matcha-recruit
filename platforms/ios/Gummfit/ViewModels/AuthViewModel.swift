import Foundation
import Observation

@MainActor
@Observable
final class AuthViewModel: LoadableVM {
    // Login fields
    var loginEmail = ""
    var loginPassword = ""

    // Signup fields
    var email = ""
    var password = ""
    var displayName = ""
    var accountType: AccountType = .business

    var isLoading = false
    var error: String?

    enum LoginFailureAction: Equatable { case verifyPending, showError(String) }

    /// Dispatches a login-failure HTTP status+detail to an action. Server
    /// (server/app/cappe/routes/auth.py): 401 = wrong email/password; 403
    /// "Account is not active" = suspended; 403 "confirm your email…" =
    /// unverified ⇒ verify screen.
    static func loginFailureAction(status: Int, detail: String) -> LoginFailureAction {
        guard status == 403 else { return .showError(detail) }
        return detail.lowercased().contains("confirm your email") ? .verifyPending : .showError(detail)
    }

    /// login/retryLoginAfterVerify pattern-match `APIError.httpError` to
    /// route 403-unverified to the verify screen, so they keep their own
    /// do/catch rather than `withLoad` — but still clear `error` up front
    /// the same way withLoad does, so a repeat attempt doesn't show a stale
    /// message if the new attempt also fails to produce one.
    func login(appState: AppState) async {
        isLoading = true; defer { isLoading = false }
        error = nil
        do {
            let response = try await AuthService.shared.login(email: loginEmail, password: loginPassword)
            appState.didLogin(response)
        } catch let APIError.httpError(status, detail) {
            switch Self.loginFailureAction(status: status, detail: detail) {
            case .verifyPending:
                appState.pendingCredentials = (loginEmail, loginPassword)
                appState.phase = .verifyPending(email: loginEmail)
            case .showError(let message):
                self.error = message
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func signup(appState: AppState) async {
        let req = CappeSignupRequest(
            email: email,
            password: password,
            name: displayName.isEmpty ? nil : displayName,
            account_type: accountType.rawValue
        )
        await withLoad {
            let response = try await AuthService.shared.signup(req)
            if let tokens = response.sessionTokens {
                appState.route(tokens.account)
            } else {
                appState.pendingCredentials = (self.email, self.password)
                appState.phase = .verifyPending(email: response.email)
            }
        }
    }

    func resend(email: String) async {
        await withLoad {
            try await AuthService.shared.resendVerification(email: email)
        }
    }

    /// "I've verified — sign me in": retries the credentials AppState
    /// retained since the login/signup attempt that led here. Falls back to
    /// a generic error asking the user to log in manually if the app was
    /// relaunched in between (AppState.pendingCredentials is memory-only).
    func retryLoginAfterVerify(appState: AppState) async {
        guard let creds = appState.pendingCredentials else {
            self.error = "Please log in again."
            appState.phase = .loggedOut
            return
        }
        isLoading = true; defer { isLoading = false }
        error = nil
        do {
            let response = try await AuthService.shared.login(email: creds.email, password: creds.password)
            appState.didLogin(response)
        } catch let APIError.httpError(status, detail) {
            switch Self.loginFailureAction(status: status, detail: detail) {
            case .verifyPending: self.error = "Not verified yet."
            case .showError(let message): self.error = message
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func verifyPastedToken(_ token: String, appState: AppState) async {
        guard !token.isEmpty else { return }
        await withLoad {
            let response = try await AuthService.shared.verify(token: token)
            appState.didLogin(response)
        }
    }
}
