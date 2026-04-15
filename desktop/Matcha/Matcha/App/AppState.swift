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
    private var heartbeatTask: Task<Void, Never>?
    private var inboxPollTask: Task<Void, Never>?

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
        MatchaWorkService.shared.updateCacheScope(nil)
        APIClient.shared.accessToken = nil
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
    }

    private func restoreSession() async {
        guard let user = await AuthService.shared.restoreSession() else { return }
        await MainActor.run {
            didLogin(user: user)
        }
    }

    private func startInboxPolling() {
        inboxPollTask?.cancel()
        inboxPollTask = Task {
            while !Task.isCancelled {
                do {
                    let count = try await InboxService.shared.getUnreadCount()
                    await MainActor.run { unreadInboxCount = count }
                } catch { }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    private func startPresenceHeartbeat() {
        heartbeatTask?.cancel()
        heartbeatTask = Task {
            while !Task.isCancelled {
                do {
                    try await MatchaWorkService.shared.sendHeartbeat()
                    let users = try await MatchaWorkService.shared.fetchOnlineUsers()
                    await MainActor.run { onlineUsers = users }
                } catch {
                    // Non-critical — silently continue
                }
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }
}
