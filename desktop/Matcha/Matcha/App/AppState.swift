import Foundation

@Observable
class AppState {
    var isAuthenticated: Bool = false
    var currentUser: UserInfo? = nil
    var selectedThreadId: String? = nil
    var showSkills: Bool = false
    var onlineUsers: [MWOnlineUser] = []
    private var heartbeatTask: Task<Void, Never>?

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
    }

    @MainActor
    func didLogout() {
        currentUser = nil
        isAuthenticated = false
        selectedThreadId = nil
        showSkills = false
        onlineUsers = []
        heartbeatTask?.cancel()
        heartbeatTask = nil
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
