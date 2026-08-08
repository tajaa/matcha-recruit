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

    func login(appState: AppState) async {
        isLoading = true; defer { isLoading = false }
        error = nil
        do {
            let response = try await AuthService.shared.login(email: loginEmail, password: loginPassword)
            appState.didLogin(response)
        } catch APIError.httpError(403, _) {
            pendingCredentials = (loginEmail, loginPassword)
            appState.phase = .verifyPending(email: loginEmail)
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
        } catch APIError.httpError(403, _) {
            self.error = "Not verified yet."
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
