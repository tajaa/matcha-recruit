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
    var currentUserID: String?
    var unreadMessages = 0
    var unreadNotifications = 0
    var pendingConversationID: String?
    private var pendingURL: URL?

    init() {
        APIClient.shared.onUnauthorized = { [weak self] in
            AuthService.shared.clearLocalSession()
            self?.clearUserState()
        }
    }

    func restore() async {
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

    func signOut() async throws {
        do {
            try await PushService.shared.unregister()
            try await AuthService.shared.logout()
            clearUserState()
        } catch {
            await PushService.shared.register()
            throw error
        }
    }

    func handlePush(_ payload: [AnyHashable: Any]) {
        guard case .ready = phase else { return }
        AppDelegate.pendingNotification = nil
        if let destination = PushRoute.destination(for: payload) { navigate(to: destination) }
        Task { await refreshBadges() }
    }

    func handleURL(_ url: URL) {
        guard url.scheme == "matchaschedule" else { return }
        guard case .ready = phase else { pendingURL = url; return }
        if let destination = PushRoute.destination(for: url) { navigate(to: destination) }
    }

    private func navigate(to destination: PushDestination) {
        switch destination {
        case .schedule: selectedTab = 0
        case .requests: selectedTab = 1
        case .inbox(let id):
            pendingConversationID = id
            selectedTab = 2
        }
    }

    func refreshBadges() async {
        async let messages = InboxService.shared.unreadCount()
        async let notices = NotificationService.unreadCount()
        if let count = try? await messages { unreadMessages = count }
        if let count = try? await notices { unreadNotifications = count }
    }

    private func clearUserState() {
        phase = .signedOut
        currentUserID = nil
        unreadMessages = 0
        unreadNotifications = 0
        pendingConversationID = nil
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
        currentUserID = me.user.id
        phase = .ready(profile)
        if let payload = AppDelegate.pendingNotification {
            AppDelegate.pendingNotification = nil
            handlePush(payload)
        }
        if let pendingURL {
            self.pendingURL = nil
            handleURL(pendingURL)
        }
        Task {
            await PushService.shared.activate()
            await refreshBadges()
        }
    }
}
