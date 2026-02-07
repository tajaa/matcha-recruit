import Foundation
import Combine

enum AuthState {
    case unknown
    case unauthenticated
    case authenticated(CurrentUser)
}

@MainActor
final class AuthViewModel: ObservableObject {
    @Published private(set) var state: AuthState = .unknown
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let apiClient = APIClient.shared
    private let tokenManager = TokenManager.shared

    var isAuthenticated: Bool {
        if case .authenticated = state { return true }
        return false
    }

    var currentUser: CurrentUser? {
        if case .authenticated(let user) = state { return user }
        return nil
    }

    var interviewPrepTokens: Int {
        currentUser?.interviewPrepTokens ?? 0
    }

    var allowedInterviewRoles: [String] {
        currentUser?.allowedInterviewRoles ?? []
    }

    // MARK: - Initialization

    func checkAuthStatus() async {
        guard tokenManager.isAuthenticated else {
            state = .unauthenticated
            return
        }

        do {
            let response = try await apiClient.getCurrentUser()
            state = .authenticated(response.user)
        } catch let error as APIError {
            // Clear stored tokens only for explicit auth failures.
            switch error {
            case .unauthorized, .tokenRefreshFailed:
                tokenManager.clearTokens()
            default:
                break
            }
            state = .unauthenticated
        } catch {
            state = .unauthenticated
        }
    }

    // MARK: - Login

    func login(email: String, password: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "Please enter email and password"
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            _ = try await apiClient.login(email: email, password: password)
            let userResponse = try await apiClient.getCurrentUser()
            state = .authenticated(userResponse.user)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - Logout

    func logout() {
        apiClient.logout()
        state = .unauthenticated
    }

    // MARK: - Refresh User

    func refreshUser() async {
        guard isAuthenticated else { return }

        do {
            let response = try await apiClient.getCurrentUser()
            state = .authenticated(response.user)
        } catch {
            // Silently fail refresh
            print("Failed to refresh user: \(error)")
        }
    }
}
