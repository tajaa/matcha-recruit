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
    /// The store's clock, learned with the schedule. Date pickers pick store
    /// days, which is what the server compares against.
    var storeTimeZone: TimeZone?
    private var pendingURL: URL?

    /// Keychain items outlive an uninstall. Without this a reinstall would
    /// silently restore the previous user's session on a shared phone.
    static let hasLaunchedKey = "schedule.hasLaunched"

    init() {
        APIClient.shared.onUnauthorized = { [weak self] in
            AuthService.shared.clearLocalSession()
            self?.clearUserState()
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
            // Also drops a push tapped to launch the app: nobody is signed in
            // to route it for, and it must not route whoever signs in next.
            clearUserState()
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
                clearUserState()
            } else {
                phase = .retry(error.localizedDescription)
            }
        }
    }

    func signIn(email: String, password: String) async throws {
        _ = try await AuthService.shared.login(email: email, password: password)
        try await loadProfile()
    }

    /// Never fails. Revoke the device session FIRST: it needs only the stored
    /// refresh token, and the server drops every push token bound to that
    /// session plus ours explicitly. Calling anything that needs an access
    /// token first let an idle-expired session's 401 → failed refresh wipe the
    /// refresh token, so the revoke was never sent and the phone kept the
    /// user's pushes. Offline: local state is cleared anyway and the revoke is
    /// queued (see AuthService.logout).
    func signOut() async {
        await AuthService.shared.logout(pushToken: PushService.shared.currentToken)
        PushService.shared.markSignedOut()
        clearUserState()
    }

    func handlePush(_ payload: [AnyHashable: Any]) {
        guard case .ready = phase else {
            // While restoring, keep it for loadProfile. Signed out: nobody to
            // route it for — it must not route the next person to sign in.
            if case .signedOut = phase { AppDelegate.pendingNotification = nil }
            return
        }
        AppDelegate.pendingNotification = nil
        if let destination = PushRoute.destination(for: payload) { navigate(to: destination) }
        Task { await refreshBadges() }
    }

    func handleURL(_ url: URL) {
        guard url.scheme == "matchaschedule" else { return }
        guard case .ready = phase else {
            if case .signedOut = phase { return }
            pendingURL = url
            return
        }
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

    /// Badge refresh for foreground pushes and returning to the app; a no-op
    /// until someone is signed in.
    func refreshBadgesIfReady() async {
        guard case .ready = phase else { return }
        await refreshBadges()
    }

    func refreshBadges() async {
        async let messages = InboxService.shared.unreadCount()
        async let notices = NotificationService.unreadCount()
        if let count = try? await messages { unreadMessages = count }
        if let count = try? await notices { unreadNotifications = count }
    }

    /// Everything tied to the signed-in person, including a push or link
    /// tapped while signed out: it must not route whoever signs in next.
    func clearUserState() {
        phase = .signedOut
        currentUserID = nil
        unreadMessages = 0
        unreadNotifications = 0
        pendingConversationID = nil
        storeTimeZone = nil
        pendingURL = nil
        AppDelegate.pendingNotification = nil
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
