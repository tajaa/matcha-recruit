import Foundation
import UserNotifications
import SwiftUI
import AppKit

/// One open workspace tab. Home is permanent + non-closable; up to
/// `AppState.maxPinnedTabs` others (project/channel/thread/journal) can be
/// pinned alongside it. `title` is cached at pin time and refreshed when the
/// underlying view loads, so a rename eventually reflects without a stale id.
struct WorkTab: Codable, Hashable, Identifiable {
    enum Kind: String, Codable { case home, project, channel, thread, journal }
    var kind: Kind
    var entityId: String
    var title: String

    var id: String { kind == .home ? "home" : "\(kind.rawValue):\(entityId)" }
    static let home = WorkTab(kind: .home, entityId: "", title: "Home")

    var icon: String {
        switch kind {
        case .home: return "house"
        case .project: return "folder"
        case .channel: return "number"
        case .thread: return "bubble.left"
        case .journal: return "book.closed"
        }
    }
}

@Observable
class AppState {
    var isAuthenticated: Bool = false
    var currentUser: UserInfo? = nil
    var selectedThreadId: String? = nil
    var selectedProjectId: String? = nil
    var selectedChannelId: String? = nil
    var selectedJournalId: String? = nil
    /// When set, the main window shows a second (pinned) detail pane beside the
    /// primary one — the in-window split. nil = no split. Reuses AuxWindowTarget.
    var splitTarget: AuxWindowTarget? = nil
    /// Deep-link hint: when set, the project detail view switches its collab
    /// panel to this tab once it mounts/updates, then clears it. Used by
    /// notification taps so a task notification opens the kanban board.
    var pendingProjectPanel: CollabRightPanel? = nil

    // MARK: - Workspace tabs
    static let maxPinnedTabs = 4
    private static let tabsKey = "mw-open-tabs-v1"
    /// Open tabs; Home is always element 0. Persisted across launches.
    var openTabs: [WorkTab] = AppState.loadTabs() {
        didSet { AppState.saveTabs(openTabs) }
    }
    /// The currently-displayed destination (drives tab highlight + what "+" pins).
    var activeTab: WorkTab = .home

    var showSkills: Bool = false
    var showInbox: Bool = false
    var showPeople: Bool = false
    var showHome: Bool = false
    /// Full-pane "Browse Channels" surface. Reached from the sidebar Channels
    /// section header. Mutually exclusive with thread/project/channel/journal
    /// selection — toggling on clears those.
    var showChannelBrowse: Bool = false
    var onlineUsers: [MWOnlineUser] = []
    var unreadInboxCount: Int = 0
    var notificationsUnreadCount: Int = 0
    var isPlusActive: Bool = false
    var betaFeatures: [String: Bool] = [:]
    var isSceneActive: Bool = true
    /// Bumped each time the app regains focus (scene active OR
    /// `NSApplication.didBecomeActiveNotification`). The open channel view
    /// observes this to REST-refetch missed messages, since a WS reconnect
    /// replays `join_room` but does not backfill the gap.
    var foregroundTick: Int = 0
    /// Throttle gate for onSceneActive — refocus fires far more often than the
    /// refresh work needs to run.
    private var lastSceneActiveAt = Date.distantPast
    /// True when notifications were previously denied — drives the in-app
    /// alert that asks the user to re-enable them via System Settings.
    /// macOS won't re-show the system dialog after the user denies once,
    /// so we surface our own prompt on every app activate.
    var showNotificationReprompt: Bool = false
    var showChannelAdminWizard: Bool = false
    var channelAdminWizardMode: ChannelAdminWizardMode = .create
    var showCollabProjectWizard: Bool = false
    var collabProjectWizardMode: CollabProjectWizardMode = .create

    // Theme storage and properties
    var appTheme: String = UserDefaults.standard.string(forKey: "mw-theme") ??
        (UserDefaults.standard.bool(forKey: "mw-chat-theme") ? "light" : "dark") {
        didSet {
            UserDefaults.standard.set(appTheme, forKey: "mw-theme")
            UserDefaults.standard.set(appTheme == "light", forKey: "mw-chat-theme")
        }
    }

    var themeBg: Color {
        switch appTheme {
        case "light": return Color.grayBg
        case "cappuchin": return Color.cappuchinDark
        default: return Color.zinc950
        }
    }

    var themeCard: Color {
        switch appTheme {
        case "light": return Color.grayCard
        case "cappuchin": return Color.cappuchinCard
        default: return Color.zinc900
        }
    }

    var themeBorder: Color {
        switch appTheme {
        case "light": return Color.grayBorder
        case "cappuchin": return Color.cappuchinBorder
        default: return Color.white.opacity(0.1)
        }
    }

    var themeAccent: Color {
        switch appTheme {
        case "light": return Color.grayAccent
        case "cappuchin": return Color.cappuchinAccent
        default: return Color.matcha500
        }
    }

    var themeAccentDark: Color {
        switch appTheme {
        case "light": return Color.grayAccentDark
        case "cappuchin": return Color.cappuchinAccentDark
        default: return Color.matcha600
        }
    }

    var themeText: Color {
        switch appTheme {
        case "light": return Color.grayText
        case "cappuchin": return Color.cappuchinText
        default: return Color.white
        }
    }

    /// Foreground for content sitting ON the accent color (e.g. button labels).
    /// Caramel cappuchin accent is light, so it needs dark text; charcoal and
    /// matcha green accents need white.
    var themeOnAccent: Color {
        switch appTheme {
        case "cappuchin": return Color.cappuchinDark
        default: return Color.white
        }
    }

    var themeTextSecondary: Color {
        switch appTheme {
        case "light": return Color.grayTextSecondary
        case "cappuchin": return Color.cappuchinSecondary
        default: return Color.secondary
        }
    }

    var lightMode: Bool {
        return appTheme == "light"
    }

    var mwBetaLite: Bool {
        betaFeatures["matcha_work_beta_lite"] == true || betaFeatures["matcha_work_beta_full"] == true
    }
    var mwBetaFull: Bool {
        betaFeatures["matcha_work_beta_full"] == true
    }
    /// Bumped whenever a channel is created/joined/left so observing views
    /// reload their lists. Pairs with the existing `.mwChannelCreated`
    /// NotificationCenter signal — belt-and-suspenders for SwiftUI view
    /// hierarchies where `.onReceive` hasn't fired reliably.
    var channelsListGeneration: Int = 0
    var projectsListGeneration: Int = 0
    var journalsListGeneration: Int = 0
    /// Per-channel unread increments from WebSocket — cleared after API refresh or on channel open.
    var channelUnreadOverrides: [String: Int] = [:]
    private var heartbeatTask: Task<Void, Never>?
    private var inboxPollTask: Task<Void, Never>?
    private var notificationPollTask: Task<Void, Never>?
    private var newNotificationObserver: NSObjectProtocol?

    init() {
        APIClient.shared.onUnauthorized = { [weak self] in
            guard let self else { return }
            Task { @MainActor in
                self.didLogout()
            }
        }
        Self.migrateLegacyKeychainTokens()
        Task {
            await restoreSession()
        }
    }

    /// One-shot migration for users on older DEBUG builds that wrote JWT
    /// tokens to UserDefaults instead of the Keychain. Reads any legacy
    /// values, copies them into Keychain (the only path the post-2026-05-18
    /// `KeychainHelper` reads from), then clears the UserDefaults keys so
    /// the plaintext copy stops sitting on disk.
    private static func migrateLegacyKeychainTokens() {
        let defaults = UserDefaults.standard
        let keys = [KeychainHelper.Keys.accessToken, KeychainHelper.Keys.refreshToken]
        for key in keys {
            guard let legacy = defaults.string(forKey: key), !legacy.isEmpty else {
                continue
            }
            if KeychainHelper.load(key: key) == nil {
                KeychainHelper.save(key: key, value: legacy)
            }
            defaults.removeObject(forKey: key)
        }
    }

    @MainActor
    func didLogin(user: UserInfo) {
        currentUser = user
        isAuthenticated = true
        MatchaWorkService.shared.updateCacheScope(user.id)
        ChannelStarStore.shared.bind(userId: user.id)
        SidebarSectionOrderStore.shared.bind(userId: user.id)
        startPresenceHeartbeat()
        startInboxPolling()
        startNotificationPolling()
        Task { await refreshSubscription() }
        Task { await refreshBetaFeatures() }
        promptForNotificationsIfNeeded()
        ChannelsWebSocket.shared.onMessageGlobal = { [weak self] msg in
            guard let self else { return }
            let isSelf = msg.senderId == self.currentUser?.id
            let isCurrentChannel = self.selectedChannelId == msg.channelId
            let active = self.isSceneActive
            let enabled = ChannelNotificationManager.shared.appNotificationsEnabled
            print(
                "[AppState] onMessageGlobal channel=\(msg.channelId) "
                + "self=\(isSelf) current=\(isCurrentChannel) "
                + "sceneActive=\(active) enabled=\(enabled)"
            )
            // Ignore own messages — sender already sees their own send.
            guard !isSelf else { return }
            let channelName = ChannelsWebSocket.shared.roomName(for: msg.channelId) ?? "channel"
            // Frontmost is the right signal, not scenePhase: macOS leaves
            // scenePhase `.active` when Werk is merely behind another app, and
            // only flips to background once every window is minimized/hidden.
            // `NSApp.isActive` is true only when Werk is the focused app.
            let appFrontmost = NSApplication.shared.isActive

            if !isCurrentChannel {
                Task { @MainActor in
                    self.channelUnreadOverrides[msg.channelId, default: 0] += 1
                }
                // In-app chime only when Werk is frontmost — when it isn't, the
                // macOS banner below carries `.default` sound, so playing this
                // too would double up.
                if appFrontmost {
                    ChannelNotificationManager.shared.playInAppSound()
                }

                // In-app toast — pops in the top-right when the user is in Werk
                // (frontmost) but on another channel / view. When Werk isn't
                // frontmost the macOS banner below covers it instead, so we
                // don't double-cue.
                if ChannelNotificationManager.shared.appNotificationsEnabled,
                   appFrontmost {
                    print("[AppState] pushing channel toast — \(msg.senderName) in \(channelName)")
                    let isAttachmentOnly =
                        msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        && !msg.attachments.isEmpty
                    Task { @MainActor in
                        ChannelToastCenter.shared.push(
                            ChannelToastCenter.Toast(
                                channelId: msg.channelId,
                                channelName: channelName,
                                senderName: msg.senderName,
                                content: msg.content,
                                isAttachmentOnly: isAttachmentOnly,
                            )
                        )
                    }
                }
            }

            // macOS banner — fires whenever Werk isn't the frontmost app
            // (minimized, hidden, or behind another window). The willPresent
            // delegate opts it into a banner+sound even if the process is
            // technically active. Stays silent only when the user is actually
            // looking at Werk (toast handles that case in-app). The global
            // app-notifications toggle in Settings still mutes everything.
            //
            // Empty-content (image-only) messages fall back to a
            // "📎 sent an attachment" body so the OS toast doesn't
            // render a blank line under the sender's name.
            if !appFrontmost
                && ChannelNotificationManager.shared.appNotificationsEnabled {
                let bodyText: String
                if msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    bodyText = msg.attachments.isEmpty ? "" : "📎 sent an attachment"
                } else {
                    bodyText = msg.content
                }
                ChannelNotificationManager.shared.post(
                    senderName: msg.senderName,
                    content: bodyText,
                    channelName: channelName,
                )
            }
        }

        // Global broadcast WS handlers — must persist across view changes so a
        // viewer in any view (or none) reacts when an owner goes live.
        // Per-view wiring in ChannelDetailView would race/overwrite when the
        // shared singleton's callbacks were set by the most recent view.
        let bsvc = BroadcastService.shared
        ChannelsWebSocket.shared.onBroadcastStarted = { event in
            print("[AppState] WS broadcast.started channel=\(event.channelId)")
            Task { @MainActor in await bsvc.handleBroadcastStarted(event) }
        }
        ChannelsWebSocket.shared.onBroadcastEnded = { event in
            print("[AppState] WS broadcast.ended channel=\(event.channelId)")
            Task { @MainActor in await bsvc.handleBroadcastEnded(event) }
        }
        ChannelsWebSocket.shared.onBroadcastPublisherChanged = { event in
            Task { @MainActor in bsvc.handlePublisherChanged(event) }
        }
        ChannelsWebSocket.shared.onBroadcastTokenGrant = { event in
            Task { @MainActor in
                await bsvc.handleTokenGrant(channelId: event.channelId,
                                            token: event.token,
                                            liveKitUrl: event.liveKitUrl,
                                            canPublish: event.canPublish)
            }
        }

        subscribeNewNotificationObserver()
    }

    /// Wire the `.mwNewNotification` push fan-out — fired by ChannelsWebSocket
    /// when the server pushes a `notification` event. Bumps the bell count,
    /// reconciles via a single REST refetch (handles missed pushes during
    /// reconnect), and fires a macOS UNNotification toast for non-channel
    /// types (channel-chat toasts still go through the starred-channel path
    /// in onMessageGlobal to avoid double-notifying).
    @MainActor
    private func subscribeNewNotificationObserver() {
        if let token = newNotificationObserver {
            NotificationCenter.default.removeObserver(token)
        }
        newNotificationObserver = NotificationCenter.default.addObserver(
            forName: .mwNewNotification,
            object: nil,
            queue: .main
        ) { [weak self] note in
            guard let self else { return }
            let n = note.userInfo?["notification"] as? [String: Any]
            let type = n?["type"] as? String ?? ""
            Task { @MainActor in
                // Bell badge ticks for every notification type so kanban
                // moves, channel messages, mentions all show up. Refresh
                // the count from server to stay in sync if the user
                // dismissed something on another device.
                self.notificationsUnreadCount += 1
                await self.refreshNotificationsCount()
                NotificationCenter.default.post(name: .mwNotificationsRefresh, object: nil)
                // OS toast is owned by the starred-channel path in
                // `onMessageGlobal` for channel_* events — skip those here
                // to avoid double-toasting on chat. Non-channel events
                // (task_assigned, task_progress, mentions, etc.) get the
                // toast directly from the bell-push.
                let isChannel = type.hasPrefix("channel_")
                if !self.isSceneActive && !isChannel {
                    let title = n?["title"] as? String ?? "Notification"
                    let body = n?["body"] as? String
                    ChannelNotificationManager.shared.postSystem(title: title, body: body)
                }
            }
        }
    }

    @MainActor
    func clearChannelUnread(_ channelId: String) {
        channelUnreadOverrides.removeValue(forKey: channelId)
    }

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
    func didLogout() {
        currentUser = nil
        isAuthenticated = false
        selectedThreadId = nil
        showSkills = false
        onlineUsers = []
        unreadInboxCount = 0
        selectedProjectId = nil
        selectedChannelId = nil
        selectedJournalId = nil
        showInbox = false
        showPeople = false
        showHome = false
        showChannelBrowse = false
        ChannelsWebSocket.shared.disconnect()
        ChannelStarStore.shared.bind(userId: nil)
        SidebarSectionOrderStore.shared.bind(userId: nil)
        heartbeatTask?.cancel()
        heartbeatTask = nil
        inboxPollTask?.cancel()
        inboxPollTask = nil
        notificationPollTask?.cancel()
        notificationPollTask = nil
        notificationsUnreadCount = 0
        if let token = newNotificationObserver {
            NotificationCenter.default.removeObserver(token)
            newNotificationObserver = nil
        }
        betaFeatures = [:]
        ChannelsWebSocket.shared.onMessageGlobal = nil
        ChannelsWebSocket.shared.onBroadcastStarted = nil
        ChannelsWebSocket.shared.onBroadcastEnded = nil
        ChannelsWebSocket.shared.onBroadcastPublisherChanged = nil
        ChannelsWebSocket.shared.onBroadcastTokenGrant = nil
        Task { await BroadcastService.shared.leave() }
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
        // Always keep the socket alive (idempotent, cheap).
        ChannelsWebSocket.shared.connect()
        // Throttle the rest: refocus fires on every Cmd-Tab; running the full
        // refresh each time made the app visibly re-render. Once per 10s.
        if Date().timeIntervalSince(lastSceneActiveAt) < 10 { return }
        lastSceneActiveAt = Date()
        await refreshSubscription()
        await refreshBetaFeatures()
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

    /// Surface the notification-permission prompt on every app open when
    /// status is anything other than `.authorized`. macOS only shows the
    /// OS dialog once per install, so the in-app alert is the only way to
    /// nudge denied / provisional / ephemeral users. The user can mute the
    /// alert permanently via "Don't ask again".
    /// Called from both `didLogin` (cold launch: restoreSession → didLogin
    /// completes after scenePhase fires, so onSceneActive's early-return
    /// would otherwise miss the check) and `onSceneActive` (warm reopen).
    @MainActor
    private func promptForNotificationsIfNeeded() {
        guard !ChannelNotificationManager.shared.promptSuppressed else { return }
        ChannelNotificationManager.shared.checkAuthorizationStatus { [weak self] status in
            guard let self else { return }
            switch status {
            case .authorized:
                return
            case .notDetermined:
                // First-ever launch: fire OS dialog only. The in-app alert
                // would double-nag legitimate users who immediately click
                // Allow. If macOS Focus/MDM/DND suppresses the OS dialog,
                // the next scene activation reads back .denied and the
                // alert fires then.
                ChannelNotificationManager.shared.requestPermission()
            default:
                // .denied, .provisional, .ephemeral — all show the alert
                self.showNotificationReprompt = true
            }
        }
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

    // MARK: - Workspace tabs

    private static func loadTabs() -> [WorkTab] {
        guard let data = UserDefaults.standard.data(forKey: tabsKey),
              let tabs = try? JSONDecoder().decode([WorkTab].self, from: data),
              !tabs.isEmpty
        else { return [.home] }
        // Home must always lead.
        return tabs.first?.kind == .home ? tabs : [.home] + tabs.filter { $0.kind != .home }
    }

    private static func saveTabs(_ tabs: [WorkTab]) {
        if let data = try? JSONEncoder().encode(tabs) {
            UserDefaults.standard.set(data, forKey: tabsKey)
        }
    }

    var pinnedTabCount: Int { openTabs.filter { $0.kind != .home }.count }
    var canPinActiveTab: Bool {
        activeTab.kind != .home
            && !openTabs.contains(where: { $0.id == activeTab.id })
            && pinnedTabCount < AppState.maxPinnedTabs
    }

    /// Switch the detail pane to a tab's destination.
    @MainActor
    func selectTab(_ tab: WorkTab) {
        activeTab = tab
        navigateToDestination(tab)
    }

    /// Pin the currently-open item as a tab (no-op for Home / duplicates / when full).
    @MainActor
    func pinActiveTab() {
        guard canPinActiveTab else { return }
        openTabs.append(activeTab)
    }

    @MainActor
    func closeTab(_ tab: WorkTab) {
        guard tab.kind != .home else { return }
        openTabs.removeAll { $0.id == tab.id }
        if activeTab.id == tab.id { selectTab(.home) }
    }

    /// Called by a detail view once its data loads: marks it active and
    /// refreshes the cached title on any matching pinned tab.
    @MainActor
    func setActiveContext(_ tab: WorkTab) {
        activeTab = tab
        if let idx = openTabs.firstIndex(where: { $0.id == tab.id }), openTabs[idx].title != tab.title {
            openTabs[idx].title = tab.title
        }
    }

    @MainActor
    private func navigateToDestination(_ tab: WorkTab) {
        selectedProjectId = nil
        selectedThreadId = nil
        selectedChannelId = nil
        selectedJournalId = nil
        showHome = false
        showSkills = false
        showInbox = false
        showPeople = false
        showChannelBrowse = false
        switch tab.kind {
        case .home: showHome = true
        case .project: selectedProjectId = tab.entityId
        case .channel: selectedChannelId = tab.entityId
        case .thread: selectedThreadId = tab.entityId
        case .journal: selectedJournalId = tab.entityId
        }
    }

    /// Navigate to the object a notification points at. Most notifications
    /// carry the target in `metadata` (project_id / task_id / thread_id /
    /// channel_id / journal_id) with a bare `/work` link; task notifications
    /// also encode it in the link query (`?project=&task=`). We prefer
    /// metadata and fall back to the link query, so either shape navigates.
    /// Mirrors the surface-clearing the sidebar / home buttons do.
    @MainActor
    func handleNotificationLink(_ link: String?, metadata: [String: String]? = nil) {
        // Link query params (if any).
        let items = link.flatMap { URLComponents(string: $0)?.queryItems } ?? []
        func query(_ key: String) -> String? {
            items.first(where: { $0.name == key })?.value.flatMap { $0.isEmpty ? nil : $0 }
        }
        func meta(_ key: String) -> String? {
            metadata?[key].flatMap { $0.isEmpty ? nil : $0 }
        }
        // Prefer metadata's `<thing>_id`, fall back to link's `<thing>`.
        func target(_ name: String) -> String? { meta("\(name)_id") ?? query(name) }

        let project = target("project")
        let task = target("task")
        let thread = target("thread")
        let channel = target("channel")
        let journal = target("journal")

        func clearSurfaces() {
            showHome = false
            showSkills = false
            showInbox = false
            showPeople = false
            showChannelBrowse = false
        }

        if let project {
            clearSurfaces()
            selectedThreadId = nil
            selectedJournalId = nil
            selectedChannelId = nil
            selectedProjectId = project
            // A task notification should land on the kanban board, not chat.
            pendingProjectPanel = task != nil ? .kanban : nil
        } else if let thread {
            clearSurfaces()
            selectedProjectId = nil
            selectedJournalId = nil
            selectedChannelId = nil
            selectedThreadId = thread
        } else if let channel {
            clearSurfaces()
            selectedProjectId = nil
            selectedThreadId = nil
            selectedJournalId = nil
            selectedChannelId = channel
        } else if let journal {
            clearSurfaces()
            selectedProjectId = nil
            selectedThreadId = nil
            selectedChannelId = nil
            selectedJournalId = journal
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

/// What a secondary (aux) window is pinned to. Codable + Hashable so it can be
/// passed as a WindowGroup presentation value via `openWindow(id:value:)`.
/// Each detail view it maps to is rendered with `isEmbedded: true` so it never
/// writes the shared nav/tab context of the main window.
enum AuxWindowTarget: Codable, Hashable {
    case project(String)
    case channel(String)
    case thread(String)
    case journal(String)
}
