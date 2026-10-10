import Foundation
import Observation

enum AppPhase {
    case restoring
    case signedOut
    case ready(Session)
    case needsWeb
    case disabled
    case retry(String)
}

/// Who is signed in. Crew have an employee profile; a business admin has a
/// manager scope; a store manager has both.
struct Session: Equatable {
    let userID: String
    let role: String
    let displayName: String
    let companyName: String
    let employee: EmployeeProfile?
    let manager: ManagerScope?

    var canManage: Bool { manager?.can_manage == true }
    var isBusinessAdmin: Bool { role == "client" }
}

extension EmployeeProfile: Equatable {
    static func == (lhs: EmployeeProfile, rhs: EmployeeProfile) -> Bool { lhs.id == rhs.id }
}

enum AppTab: Hashable {
    case schedule, requests, manage, inbox, me

    /// The tab bar for this account: crew get their own schedule and requests,
    /// managers add Manage, and a business admin (no shifts of their own) gets
    /// Manage instead. Never more than five, so nothing hides under "More".
    static func tabs(for session: Session) -> [AppTab] {
        var tabs: [AppTab] = []
        if session.employee != nil { tabs += [.schedule, .requests] }
        if session.canManage { tabs.append(.manage) }
        return tabs + [.inbox, .me]
    }
}

@MainActor @Observable
final class AppState {
    var phase: AppPhase = .restoring
    var selectedTab: AppTab = .schedule
    var currentUserID: String?
    var unreadMessages = 0
    var unreadNotifications = 0
    /// Schedule requests waiting for this manager.
    var pendingApprovals = 0
    var pendingConversationID: String?
    /// A request a push or link asked to open in Manage.
    var pendingApprovalID: String?
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
        let tabs = session.map(AppTab.tabs(for:)) ?? []
        // A destination this account has no tab for lands on Manage (a
        // business admin has no Schedule/Requests of their own).
        func open(_ tab: AppTab) {
            selectedTab = tabs.contains(tab) ? tab : (tabs.contains(.manage) ? .manage : tabs.first ?? .me)
        }
        switch destination {
        case .schedule: open(.schedule)
        case .requests: open(.requests)
        case .inbox(let id):
            pendingConversationID = id
            open(.inbox)
        case .manageApprovals(let id):
            guard tabs.contains(.manage) else { open(.requests); return }
            pendingApprovalID = id
            selectedTab = .manage
        }
    }

    var session: Session? {
        if case .ready(let session) = phase { return session }
        return nil
    }

    /// Badge refresh for foreground pushes and returning to the app; a no-op
    /// until someone is signed in.
    func refreshBadgesIfReady() async {
        guard case .ready = phase else { return }
        await refreshBadges()
    }

    func refreshBadges() async {
        let prefix = notificationPrefix
        async let messages = InboxService.shared.unreadCount()
        async let notices = NotificationService.unreadCount(typePrefix: prefix)
        if let count = try? await messages { unreadMessages = count }
        if let count = try? await notices { unreadNotifications = count }
        if session?.canManage == true, let scope = try? await ManagerService.scope() {
            pendingApprovals = scope.pending_requests
        }
    }

    /// A business admin's bell also holds their web notifications; the app
    /// shows only the schedule ones (and never marks the rest read).
    var notificationPrefix: String? { session?.isBusinessAdmin == true ? "schedule_" : nil }

    /// Everything tied to the signed-in person, including a push or link
    /// tapped while signed out: it must not route whoever signs in next.
    func clearUserState() {
        phase = .signedOut
        currentUserID = nil
        unreadMessages = 0
        unreadNotifications = 0
        pendingApprovals = 0
        pendingConversationID = nil
        pendingApprovalID = nil
        storeTimeZone = nil
        pendingURL = nil
        AppDelegate.pendingNotification = nil
    }

    private func loadProfile() async throws {
        let me: MeResponse = try await APIClient.shared.request(method: "GET", path: "/auth/me", fresh: true)
        let session: Session
        switch me.user.role {
        case "employee":
            guard let profile = me.profile else {
                phase = .needsWeb
                return
            }
            guard profile.enabled_features.employee_schedule else {
                phase = .disabled
                return
            }
            session = Session(
                userID: me.user.id, role: me.user.role, displayName: profile.displayName,
                companyName: profile.company_name, employee: profile,
                manager: try await managerScope(required: false)
            )
        case "client":
            guard let scope = try await managerScope(required: true) else { return }
            session = Session(
                userID: me.user.id, role: me.user.role,
                displayName: me.business?.name?.nilIfBlank ?? me.user.email,
                companyName: me.business?.company_name ?? "", employee: nil, manager: scope
            )
        default:
            phase = .needsWeb
            return
        }
        currentUserID = me.user.id
        pendingApprovals = session.manager?.pending_requests ?? 0
        selectedTab = AppTab.tabs(for: session).first ?? .me
        phase = .ready(session)
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

    /// The manager scope, or nil for crew. For a business admin it is the
    /// whole point of signing in: scheduling turned off (403) is `.disabled`,
    /// a server that predates manager tools is `.needsWeb`, and nil returns.
    /// A crew member just stays crew when the call is refused. Network
    /// failures throw, so the launch screen offers a retry.
    private func managerScope(required: Bool) async throws -> ManagerScope? {
        do {
            let scope = try await ManagerService.scope()
            if required && !scope.can_manage {
                phase = .needsWeb
                return nil
            }
            return scope.can_manage ? scope : nil
        } catch {
            if case APIError.httpError(let code, _) = error {
                guard required else { return nil }
                phase = code == 403 ? .disabled : .needsWeb
                return nil
            }
            // A shape this build does not know must not lock crew out.
            if !required, case APIError.decodingError = error { return nil }
            throw error
        }
    }
}

private extension String {
    var nilIfBlank: String? { trimmingCharacters(in: .whitespaces).isEmpty ? nil : self }
}
