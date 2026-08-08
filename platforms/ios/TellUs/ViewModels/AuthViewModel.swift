import Foundation
import Observation

@MainActor
@Observable
final class AuthViewModel {
    // Login fields
    var loginEmail = ""
    var loginPassword = ""

    // Signup fields
    var email = ""
    var password = ""
    var displayName = ""
    var accountType: AccountType = .consumer
    var brandName = ""
    var locationCount = "1"
    var city = ""
    var state = ""

    var isLoading = false
    var error: String?

    /// Retained so VerifyWaitView's "I've verified — sign me in" can retry
    /// login without asking the user to re-enter credentials.
    private var pendingCredentials: (email: String, password: String)?

    enum LoginFailureAction: Equatable { case verifyPending, showError(String) }

    /// Dispatches a login-failure HTTP status+detail to an action. Pure, unit-
    /// tested (Tests/AuthErrorMappingTests.swift). Server (routes/auth.py):
    /// 401 = wrong email/password; 403 "Account is not active" = suspended;
    /// 403 "Please confirm your email…" = unverified ⇒ verify screen.
    static func loginFailureAction(status: Int, detail: String) -> LoginFailureAction {
        guard status == 403 else { return .showError(detail) }
        return detail.lowercased().contains("confirm your email") ? .verifyPending : .showError(detail)
    }

    func login(appState: AppState) async {
        isLoading = true; defer { isLoading = false }
        error = nil
        do {
            let response = try await AuthService.shared.login(email: loginEmail, password: loginPassword)
            appState.didLogin(response)
        } catch let APIError.httpError(status, detail) {
            switch Self.loginFailureAction(status: status, detail: detail) {
            case .verifyPending:
                pendingCredentials = (loginEmail, loginPassword)
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
        isLoading = true; defer { isLoading = false }
        error = nil
        guard accountType == .consumer || (!brandName.isEmpty && Int(locationCount) != nil) else {
            self.error = "Brand name and location count are required."
            return
        }
        let req = SignupRequest(
            email: email,
            password: password,
            display_name: displayName.isEmpty ? nil : displayName,
            account_type: accountType.rawValue,
            brand_name: accountType == .brand ? brandName : nil,
            location_count: accountType == .brand ? Int(locationCount) : nil,
            city: city.isEmpty ? nil : city,
            state: state.isEmpty ? nil : state
        )
        do {
            let response = try await AuthService.shared.signup(req)
            if let account = response.account, response.access_token != nil {
                appState.route(account)
            } else {
                pendingCredentials = (email, password)
                appState.phase = .verifyPending(email: response.email)
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    /// "Continue with Google" — auto-creates or links a consumer account and
    /// signs in through the same funnel as login()/verify(). A cancelled
    /// Google sheet is silent, not an error banner.
    func signInWithGoogle(appState: AppState) async {
        isLoading = true; defer { isLoading = false }
        error = nil
        do {
            let idToken = try await GoogleSignInService.presentAndFetchIDToken()
            let response = try await AuthService.shared.signInWithGoogle(idToken: idToken)
            appState.didLogin(response)
        } catch is GoogleSignInService.Cancelled {
            return
        } catch let APIError.httpError(_, detail) {
            self.error = detail
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func resend(email: String) async {
        error = nil
        do {
            try await AuthService.shared.resendVerification(email: email)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    /// "I've verified — sign me in": retries the in-memory credentials.
    /// Falls back to a generic error asking the user to log in manually if
    /// this VM instance didn't see the original attempt (e.g. app relaunch).
    func retryLoginAfterVerify(appState: AppState) async {
        guard let creds = pendingCredentials else {
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
        isLoading = true; defer { isLoading = false }
        error = nil
        do {
            let response = try await AuthService.shared.verify(token: token)
            appState.didLogin(response)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
