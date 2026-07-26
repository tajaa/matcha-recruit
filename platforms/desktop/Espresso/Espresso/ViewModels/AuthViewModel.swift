import Foundation

@Observable
class AuthViewModel {
    #if DEBUG
    var email = "ashVidales+tessu@gmail.com"
    var password = ""
    #else
    var email = ""
    var password = ""
    #endif
    var errorMessage: String?
    var isLoading = false

    func login(appState: AppState) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "Please enter your email and password."
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            let response = try await AuthService.shared.login(email: email, password: password)
            await MainActor.run {
                appState.didLogin(user: response.user)
            }
        } catch let error as APIError {
            await MainActor.run {
                errorMessage = error.errorDescription
            }
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
            }
        }

        await MainActor.run {
            isLoading = false
        }
    }
}
