import Foundation

// MARK: - Background poll loops
//
// Split out of AppState.swift. All three are started by `didLogin` and
// cancelled by `didLogout`; each idles while the scene is inactive rather than
// stopping, so a refocus resumes on the next tick without re-arming.

extension AppState {

    /// Presence heartbeat + the online-user list.
    func startPresenceHeartbeat() {
        heartbeatTask?.cancel()
        heartbeatTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                if self?.isSceneActive == true {
                    do {
                        try await MatchaWorkService.shared.sendHeartbeat()
                        // Skip the explicit poll when the channels WebSocket
                        // is connected — it pushes `online_users` events
                        // automatically, so the GET is redundant load.
                        if !ChannelsWebSocket.shared.isConnected {
                            let users = try await MatchaWorkService.shared.fetchOnlineUsers()
                            self?.onlineUsers = users
                        }
                    } catch {
                        // Non-critical — silently continue
                    }
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    func startInboxPolling() {
        inboxPollTask?.cancel()
        inboxPollTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                if self?.isSceneActive == true {
                    do {
                        let count = try await InboxService.shared.getUnreadCount()
                        self?.unreadInboxCount = count
                    } catch { }
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    func startNotificationPolling() {
        notificationPollTask?.cancel()
        notificationPollTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                if self?.isSceneActive == true {
                    if let count = try? await MatchaWorkService.shared.fetchNotificationsUnreadCount() {
                        self?.notificationsUnreadCount = count
                    }
                    await self?.refreshProjectUnseenCounts()
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }
}
