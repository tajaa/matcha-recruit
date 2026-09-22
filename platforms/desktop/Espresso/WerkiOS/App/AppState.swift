import Foundation
import Observation
import UIKit
import UserNotifications

/// iOS app-wide state + session orchestrator. The lean counterpart to the macOS
/// `AppState` (which is AppKit-bound and carries window/toast/polling machinery).
/// It grows per phase; Phase 1 covers auth + session restore + WS lifecycle.
@MainActor
@Observable
final class AppState {
    // Session
    var isAuthenticated = false
    var currentUser: UserInfo?
    /// Server-resolved plan, including beta grants and Business accounts.
    var entitlements: MWEntitlements?
    var isPlusActive: Bool { entitlements?.has("go_live") == true }
    private var isLoggingOut = false

    // Login UI
    var isLoggingIn = false
    var authError: String?

    /// False until the launch-time session restore finishes, so the root view
    /// can hold a splash instead of flashing the login screen for returning
    /// users.
    var didRestore = false

    // Realtime context
    /// Channel currently on screen — lets the notification path skip the chat
    /// the user is already looking at.
    var selectedChannelId: String?
    var isSceneActive = true

    // Deep-link targets set when a push is tapped; consumed (and cleared) by the
    // tab/list views.
    var pendingChannelId: String?
    var pendingConversationId: String?
    var pendingProjectId: String?
    var pendingTaskId: String?
    private var deepLinkObserver: NSObjectProtocol?

    init() {
        #if DEBUG
        // Screenshot fixtures never restore credentials or contact a backend.
        if ProcessInfo.processInfo.arguments.contains("-espresso-preview") { didRestore = true; return }
        #endif
        // A failed token refresh anywhere in the app drops us to the login gate.
        APIClient.shared.onUnauthorized = { [weak self] in
            Task { @MainActor in self?.didLogout() }
        }
        deepLinkObserver = NotificationCenter.default.addObserver(
            forName: .werkDeepLink, object: nil, queue: .main
        ) { [weak self] note in
            Task { @MainActor in self?.handleDeepLink(note.userInfo) }
        }
        Task { await restoreSession() }
    }

    // MARK: - Auth

    func login(email: String, password: String) async {
        guard !isLoggingOut else { authError = "Finishing sign out. Please try again in a moment."; return }
        guard !isLoggingIn else { return }
        isLoggingIn = true
        authError = nil
        defer { isLoggingIn = false }
        do {
            let resp = try await AuthService.shared.login(email: email, password: password)
            didLogin(user: resp.user)
        } catch {
            authError = error.localizedDescription
        }
    }

    func restoreSession() async {
        defer { didRestore = true }
        guard let user = await AuthService.shared.restoreSession() else { return }
        didLogin(user: user)
    }

    func didLogin(user: UserInfo) {
        currentUser = user
        isAuthenticated = true
        CallService.shared.currentUserId = user.id
        MatchaWorkService.shared.updateCacheScope(user.id)
        wireRealtime()
        // Open the realtime channel socket. Background room joins + per-view
        // subscriptions are wired by the channel surface (Phase 2).
        ChannelsWebSocket.shared.connect()
        Task { await refreshSubscription() }
        requestPushAuthorization()
    }

    func logout() {
        guard !isLoggingOut else { return }
        isLoggingOut = true
        Task {
            // Unregister while this account's bearer is still available.
            await PushService.shared.unregister()
            try? await AuthService.shared.logout()
            didLogout()
            isLoggingOut = false
        }
    }

    func didLogout() {
        isAuthenticated = false
        currentUser = nil
        entitlements = nil
        selectedChannelId = nil
        pendingChannelId = nil; pendingConversationId = nil
        pendingProjectId = nil; pendingTaskId = nil
        APIClient.shared.accessToken = nil
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
        UIApplication.shared.unregisterForRemoteNotifications()
        Task { await CallService.shared.leave() }
        Task { await BroadcastService.shared.leave() }
        let ws = ChannelsWebSocket.shared
        ws.onMessageGlobal = nil
        ws.onCallStarted = nil; ws.onCallEnded = nil
        ws.onCallInvited = nil; ws.onCallParticipantsChanged = nil
        ws.onBroadcastStarted = nil; ws.onBroadcastEnded = nil
        ws.onBroadcastPublisherChanged = nil; ws.onBroadcastTokenGrant = nil
        ws.disconnect()
        MatchaWorkService.shared.updateCacheScope(nil)
        WorkDetailVMStore.shared.clearAll()
        ProjectWebSocket.shared.disconnect()
    }

    // MARK: - Realtime call/broadcast wiring

    /// Global call + broadcast socket handlers so their state updates regardless
    /// of which screen is open. Channel-chat unread uses `onMessageGlobal`
    /// (owned by the channel list). Mirrors the macOS AppState wiring.
    private func wireRealtime() {
        let ws = ChannelsWebSocket.shared
        let call = CallService.shared
        let broadcast = BroadcastService.shared
        call.currentUserId = currentUser?.id

        ws.onCallStarted = { event in Task { @MainActor in call.handleCallStarted(event) } }
        ws.onCallEnded = { event in Task { @MainActor in await call.handleCallEnded(event) } }
        ws.onCallInvited = { event in Task { @MainActor in call.handleCallInvited(event) } }
        ws.onCallParticipantsChanged = { event in Task { @MainActor in call.handleParticipantsChanged(event) } }

        ws.onBroadcastStarted = { event in Task { @MainActor in await broadcast.handleBroadcastStarted(event) } }
        ws.onBroadcastEnded = { event in Task { @MainActor in await broadcast.handleBroadcastEnded(event) } }
        ws.onBroadcastPublisherChanged = { event in Task { @MainActor in broadcast.handlePublisherChanged(event) } }
        ws.onBroadcastTokenGrant = { event in
            Task { @MainActor in
                await broadcast.handleTokenGrant(
                    channelId: event.channelId, token: event.token,
                    liveKitUrl: event.liveKitUrl, canPublish: event.canPublish
                )
            }
        }
    }

    /// Keep the last-known gates on transient failures or a future plan value.
    /// A result from a previous account must never publish into a new session.
    func refreshSubscription() async {
        guard let userId = currentUser?.id else { return }
        do {
            let result: MWEntitlements = try await APIClient.shared.request(
                method: "GET", path: "/matcha-work/entitlements"
            )
            guard currentUser?.id == userId else { return }
            entitlements = result
        } catch { /* Server authorization remains authoritative. */ }
    }

    // MARK: - Push (APNs)

    /// Ask for notification permission and, if granted, register for remote
    /// notifications. The device token lands in `AppDelegate` →
    /// `PushService.updateDeviceToken` → `POST /push/register`.
    func requestPushAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            Task { @MainActor in UIApplication.shared.registerForRemoteNotifications() }
        }
    }

    /// Decode a tapped push payload into a pending deep-link target.
    private func handleDeepLink(_ userInfo: [AnyHashable: Any]?) {
        guard let userInfo else { return }
        var meta: [String: Any] = [:]
        if let m = userInfo["metadata"] as? [String: Any] {
            meta = m
        } else if let m = userInfo["metadata"] as? [AnyHashable: Any] {
            for (k, v) in m { if let ks = k as? String { meta[ks] = v } }
        }
        pendingChannelId = nil; pendingConversationId = nil
        pendingProjectId = nil; pendingTaskId = nil
        // Set the detail before publishing the project navigation trigger.
        if let project = meta["project_id"] as? String {
            pendingTaskId = meta["task_id"] as? String
            pendingProjectId = project
        } else if let conv = meta["conversation_id"] as? String { pendingConversationId = conv }
        else if let cid = meta["channel_id"] as? String { pendingChannelId = cid }
    }
}
