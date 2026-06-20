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
    /// matcha-work personal Plus — gates go-live/calls power features. Wired in
    /// the calls phase; false until then.
    var isPlusActive = false

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
    private var deepLinkObserver: NSObjectProtocol?

    init() {
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
        wireRealtime()
        // Open the realtime channel socket. Background room joins + per-view
        // subscriptions are wired by the channel surface (Phase 2).
        ChannelsWebSocket.shared.connect()
        Task { await refreshSubscription() }
        requestPushAuthorization()
    }

    func logout() {
        Task {
            try? await AuthService.shared.logout()
            didLogout()
        }
    }

    func didLogout() {
        isAuthenticated = false
        currentUser = nil
        isPlusActive = false
        selectedChannelId = nil
        Task { await PushService.shared.unregister() }
        Task { await CallService.shared.leave() }
        Task { await BroadcastService.shared.leave() }
        let ws = ChannelsWebSocket.shared
        ws.onMessageGlobal = nil
        ws.onCallStarted = nil; ws.onCallEnded = nil
        ws.onCallInvited = nil; ws.onCallParticipantsChanged = nil
        ws.onBroadcastStarted = nil; ws.onBroadcastEnded = nil
        ws.onBroadcastPublisherChanged = nil; ws.onBroadcastTokenGrant = nil
        ws.disconnect()
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

    /// Resolve matcha-work personal Plus → `isPlusActive` (gates starting calls /
    /// going live; joining is open to all members and server-enforced).
    func refreshSubscription() async {
        do {
            let sub: MWSubscription = try await APIClient.shared.request(
                method: "GET", path: "/matcha-work/billing/subscription"
            )
            isPlusActive = sub.isPersonalPlus
        } catch {
            isPlusActive = false
        }
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
        if let cid = meta["channel_id"] as? String { pendingChannelId = cid }
        if let conv = meta["conversation_id"] as? String { pendingConversationId = conv }
    }
}
