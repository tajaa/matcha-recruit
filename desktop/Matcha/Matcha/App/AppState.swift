import Foundation

@Observable
class AppState {
    var isAuthenticated: Bool = false
    var currentUser: UserInfo? = nil
    var selectedThreadId: String? = nil
    var selectedProjectId: String? = nil
    var selectedChannelId: String? = nil
    var showSkills: Bool = false
    var showInbox: Bool = false
    var showPeople: Bool = false
    var onlineUsers: [MWOnlineUser] = []
    var unreadInboxCount: Int = 0
    var notificationsUnreadCount: Int = 0
    var isPlusActive: Bool = false
    var isSceneActive: Bool = true
    /// Bumped whenever a channel is created/joined/left so observing views
    /// reload their lists. Pairs with the existing `.mwChannelCreated`
    /// NotificationCenter signal — belt-and-suspenders for SwiftUI view
    /// hierarchies where `.onReceive` hasn't fired reliably.
    var channelsListGeneration: Int = 0
    var projectsListGeneration: Int = 0
    private var heartbeatTask: Task<Void, Never>?
    private var inboxPollTask: Task<Void, Never>?
    private var notificationPollTask: Task<Void, Never>?

    init() {
        APIClient.shared.onUnauthorized = { [weak self] in
            guard let self else { return }
            Task { @MainActor in
                self.didLogout()
            }
        }
        Task {
            await restoreSession()
        }
    }

    @MainActor
    func didLogin(user: UserInfo) {
        currentUser = user
        isAuthenticated = true
        MatchaWorkService.shared.updateCacheScope(user.id)
        startPresenceHeartbeat()
        startInboxPolling()
        startNotificationPolling()
        Task { await refreshSubscription() }
    }

    @MainActor
    func refreshSubscription() async {
        do {
            let sub = try await MatchaWorkService.shared.getPersonalSubscription()
            isPlusActive = sub.isPersonalPlus
        } catch {
            isPlusActive = false
        }
    }

    @MainActor
    func didLogout() {
        currentUser = nil
        isAuthenticated = false
        selectedThreadId = nil
        showSkills = false
        onlineUsers = []
        unreadInboxCount = 0
        selectedProjectId = nil
        selectedChannelId = nil
        showInbox = false
        showPeople = false
        ChannelsWebSocket.shared.disconnect()
        heartbeatTask?.cancel()
        heartbeatTask = nil
        inboxPollTask?.cancel()
        inboxPollTask = nil
        notificationPollTask?.cancel()
        notificationPollTask = nil
        notificationsUnreadCount = 0
        MatchaWorkService.shared.updateCacheScope(nil)
        APIClient.shared.accessToken = nil
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
    }

    func restoreSession() async {
        guard let user = await AuthService.shared.restoreSession() else { return }
        await MainActor.run {
            didLogin(user: user)
        }
    }

    /// Called when the app scene becomes active. Retries the session
    /// restore if the user is not authenticated (fixes the "started the
    /// dev server after launching the app" case) and kicks the channels
    /// WebSocket to reconnect if already authenticated.
    @MainActor
    func onSceneActive() async {
        if !isAuthenticated {
            await restoreSession()
            return
        }
        await refreshSubscription()
        // Nudge the channels socket to reconnect if it dropped.
        ChannelsWebSocket.shared.connect()
        // Best-effort heartbeat so presence flips green immediately.
        Task { try? await MatchaWorkService.shared.sendHeartbeat() }
    }

    private func startInboxPolling() {
        inboxPollTask?.cancel()
        inboxPollTask = Task { [weak self] in
            while !Task.isCancelled {
                let active = await MainActor.run { self?.isSceneActive ?? false }
                if active {
                    do {
                        let count = try await InboxService.shared.getUnreadCount()
                        await MainActor.run { self?.unreadInboxCount = count }
                    } catch { }
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    private func startNotificationPolling() {
        notificationPollTask?.cancel()
        notificationPollTask = Task { [weak self] in
            while !Task.isCancelled {
                let active = await MainActor.run { self?.isSceneActive ?? false }
                if active {
                    if let count = try? await MatchaWorkService.shared.fetchNotificationsUnreadCount() {
                        await MainActor.run { self?.notificationsUnreadCount = count }
                    }
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    /// Force a refetch of the unread count — used by the notifications popover
    /// after a mark-read or mark-all-read action so the badge updates without
    /// waiting for the next poll tick.
    @MainActor
    func refreshNotificationsCount() async {
        if let count = try? await MatchaWorkService.shared.fetchNotificationsUnreadCount() {
            notificationsUnreadCount = count
        }
    }

    private func startPresenceHeartbeat() {
        heartbeatTask?.cancel()
        heartbeatTask = Task { [weak self] in
            while !Task.isCancelled {
                let active = await MainActor.run { self?.isSceneActive ?? false }
                if active {
                    do {
                        try await MatchaWorkService.shared.sendHeartbeat()
                        // Skip the explicit poll when the channels WebSocket
                        // is connected — it pushes `online_users` events
                        // automatically, so the GET is redundant load.
                        let wsConnected = await MainActor.run { ChannelsWebSocket.shared.isConnected }
                        if !wsConnected {
                            let users = try await MatchaWorkService.shared.fetchOnlineUsers()
                            await MainActor.run { self?.onlineUsers = users }
                        }
                    } catch {
                        // Non-critical — silently continue
                    }
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }
}
