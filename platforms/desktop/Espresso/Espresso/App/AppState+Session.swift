import Foundation
import SwiftUI
import AppKit

// MARK: - Session lifecycle: login, logout, restore, scene activation
//
// Split out of AppState.swift.

extension AppState {

    /// One-shot migration for users on older DEBUG builds that wrote JWT
    /// tokens to UserDefaults instead of the Keychain. Reads any legacy
    /// values, copies them into Keychain (the only path the post-2026-05-18
    /// `KeychainHelper` reads from), then clears the UserDefaults keys so
    /// the plaintext copy stops sitting on disk.
    ///
    /// Known tradeoff: if the keychain write fails PERSISTENTLY, the
    /// plaintext copy is retained on disk indefinitely (vs. destroying the
    /// user's only credential). Acceptable because this re-runs every launch
    /// — a transient failure (keychain locked at first-unlock) self-heals on
    /// the next launch, which is exactly why the copy must survive a failure.
    static func migrateLegacyKeychainTokens() {
        let defaults = UserDefaults.standard
        let keys = [KeychainHelper.Keys.accessToken, KeychainHelper.Keys.refreshToken]
        for key in keys {
            guard let legacy = defaults.string(forKey: key), !legacy.isEmpty else {
                continue
            }
            // Only clear the UserDefaults copy once the token verifiably
            // lives in the keychain — an unconditional removeObject after a
            // failed save would destroy the only remaining copy.
            let inKeychain = KeychainHelper.load(key: key) != nil
                || KeychainHelper.save(key: key, value: legacy)
            if inKeychain {
                defaults.removeObject(forKey: key)
            }
        }
    }

    @MainActor
    func didLogin(user: UserInfo) {
        currentUser = user
        isAuthenticated = true
        UsageBeaconService.shared.start()
        CallService.shared.currentUserId = user.id
        MatchaWorkService.shared.updateCacheScope(user.id)
        ChannelStarStore.shared.bind(userId: user.id)
        JournalStarStore.shared.bind(userId: user.id)
        FileStarStore.shared.bind(userId: user.id)
        SidebarSectionOrderStore.shared.bind(userId: user.id)
        startPresenceHeartbeat()
        startInboxPolling()
        startNotificationPolling()
        Task { await refreshProjectUnseenCounts() }
        Task { await refreshSubscription() }
        Task { await refreshEntitlements() }
        Task { await refreshBetaFeatures() }
        promptForNotificationsIfNeeded()
        installRealtimeHandlers()
        subscribeNewNotificationObserver()
        subscribeBannerTapObserver()
    }

    @MainActor
    func didLogout() {
        // Idempotence guard: the 401→refresh failure path can signal
        // onUnauthorized twice (once inside the nested refresh request, once
        // in the outer catch). Re-running this teardown is harmless today,
        // but any future non-idempotent side effect (analytics event,
        // server-side revoke) would silently double — bail if already out.
        // Every real caller (onUnauthorized, Settings sign-out, ContentView)
        // fires from an authenticated session, so this never skips a first run.
        guard isAuthenticated || currentUser != nil else { return }
        currentUser = nil
        isAuthenticated = false
        UsageBeaconService.shared.stop()
        selectedThreadId = nil
        showSkills = false
        onlineUsers = []
        unreadInboxCount = 0
        selectedProjectId = nil
        selectedChannelId = nil
        selectedJournalId = nil
        selectedEmailId = nil
        showInbox = false
        showPeople = false
        showHome = false
        showChannelBrowse = false
        ChannelsWebSocket.shared.disconnect()
        ChannelStarStore.shared.bind(userId: nil)
        JournalStarStore.shared.bind(userId: nil)
        FileStarStore.shared.bind(userId: nil)
        SidebarSectionOrderStore.shared.bind(userId: nil)
        heartbeatTask?.cancel()
        heartbeatTask = nil
        inboxPollTask?.cancel()
        inboxPollTask = nil
        notificationPollTask?.cancel()
        notificationPollTask = nil
        notificationsUnreadCount = 0
        projectUnseenCounts = [:]
        channelUnreadCounts = [:]
        channelUnreadOverrides = [:]
        newNotificationTask?.cancel()
        newNotificationTask = nil
        bannerTapTask?.cancel()
        bannerTapTask = nil
        betaFeatures = [:]
        entitlements = nil
        showPaywall = false
        paywallFeature = nil
        clearRealtimeHandlers()
        MatchaWorkService.shared.updateCacheScope(nil)
        // Drop the detail-VM tier too: these retain the previous user's loaded
        // data keyed only by entity id, so leaving them would let a deep-link
        // (or same-id re-open) after a user switch repaint the prior user's data.
        WorkDetailVMStore.shared.clearAll()
        APIClient.shared.accessToken = nil
        KeychainHelper.delete(key: KeychainHelper.Keys.accessToken)
        KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
    }

    func restoreSession() async {
        let user = await AuthService.shared.restoreSession()
        // One transaction, so the splash never flickers through LoginView on
        // its way to the workspace.
        await MainActor.run {
            if let user { didLogin(user: user) }
            isRestoring = false
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
        // Always keep the socket alive (idempotent, cheap).
        ChannelsWebSocket.shared.connect()
        // Throttle the rest: refocus fires on every Cmd-Tab; running the full
        // refresh each time made the app visibly re-render. Once per 10s.
        if Date().timeIntervalSince(lastSceneActiveAt) < 10 { return }
        lastSceneActiveAt = Date()
        // Concurrent: these are three independent GETs, and running them in
        // series cost three sequential round-trips on the launch path (this
        // fires from both `scenePhase` and didBecomeActiveNotification).
        async let subscription: Void = refreshSubscription()
        async let entitlements: Void = refreshEntitlements()
        async let betaFeatures: Void = refreshBetaFeatures()
        _ = await (subscription, entitlements, betaFeatures)
        // Best-effort heartbeat so presence flips green immediately.
        Task { try? await MatchaWorkService.shared.sendHeartbeat() }
        // Kick the inbox + notification badges immediately on resume so users
        // don't see stale counts while the 60s polling loop is mid-sleep.
        Task { [weak self] in
            if let count = try? await InboxService.shared.getUnreadCount() {
                await MainActor.run { self?.unreadInboxCount = count }
            }
        }
        Task { await refreshNotificationsCount() }
        promptForNotificationsIfNeeded()
        // Nudge the open channel view to refetch (fills the gap WS reconnect leaves).
        foregroundTick &+= 1
    }

    // MARK: - Server-state refreshes

    @MainActor
    func refreshBetaFeatures() async {
        if let me = try? await AuthService.shared.fetchMe() {
            let next = me.user.betaFeatures ?? [:]
            if next != betaFeatures { betaFeatures = next }   // avoid needless re-render
        }
    }

    @MainActor
    func refreshSubscription() async {
        do {
            let sub = try await MatchaWorkService.shared.getPersonalSubscription()
            if isPlusActive != sub.isPersonalPlus { isPlusActive = sub.isPersonalPlus }
        } catch {
            if isPlusActive { isPlusActive = false }
        }
    }

    @MainActor
    func refreshEntitlements() async {
        do {
            entitlements = try await MatchaWorkService.shared.getEntitlements()
        } catch {
            // Keep the last-known plan on transient failures; never lock the
            // UI on a fetch error (server gates enforce regardless).
        }
    }
}
