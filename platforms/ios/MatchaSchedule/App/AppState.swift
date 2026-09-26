import Foundation
import Observation

enum AppPhase {
    case restoring
    case signedOut
    case ready(EmployeeProfile)
    case needsWeb
    case disabled
    case retry(String)
}

@MainActor @Observable
final class AppState {
    var phase: AppPhase = .restoring
    var selectedTab = 0

    /// Keychain items outlive an uninstall. Without this a reinstall would
    /// silently restore the previous user's session on a shared phone.
    static let hasLaunchedKey = "schedule.hasLaunched"

    init() {
        APIClient.shared.onUnauthorized = { [weak self] in
            AuthService.shared.clearLocalSession()
            self?.phase = .signedOut
        }
    }

    static func purgeKeychainOnFirstLaunch(defaults: UserDefaults = .standard) -> Bool {
        guard !defaults.bool(forKey: hasLaunchedKey) else { return false }
        KeychainHelper.Keys.all.forEach { KeychainHelper.delete(key: $0) }
        APIClient.shared.accessToken = nil
        defaults.set(true, forKey: hasLaunchedKey)
        return true
    }

    func restore() async {
        _ = Self.purgeKeychainOnFirstLaunch()
        await AuthService.shared.flushPendingRevoke()
        guard AuthService.shared.hasStoredSession else {
            phase = .signedOut
            return
        }
        phase = .restoring
        do {
            if APIClient.shared.accessToken == nil {
                _ = try await AuthService.shared.refresh()
            }
            try await loadProfile()
        } catch {
            if case APIError.unauthorized = error {
                AuthService.shared.clearLocalSession()
                phase = .signedOut
            } else {
                phase = .retry(error.localizedDescription)
            }
        }
    }

    func signIn(email: String, password: String) async throws {
        _ = try await AuthService.shared.login(email: email, password: password)
        try await loadProfile()
    }

    func signOut() async {
        await AuthService.shared.logout()
        phase = .signedOut
    }

    private func loadProfile() async throws {
        let me: MeResponse = try await APIClient.shared.request(method: "GET", path: "/auth/me")
        guard me.user.role == "employee", let profile = me.profile else {
            phase = .needsWeb
            return
        }
        guard profile.enabled_features.employee_schedule else {
            phase = .disabled
            return
        }
        phase = .ready(profile)
    }
}
