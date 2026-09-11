import Foundation
import UserNotifications
import SwiftUI
import AppKit

/// App-wide observable state: who's signed in, what the primary pane shows, and
/// the counters the chrome badges off. Behaviour is split across siblings:
///   • AppState+Session.swift          — login / logout / restore / scene-active
///   • AppState+RealtimeHandlers.swift — the channel, broadcast and call WS wiring
///   • AppState+Notifications.swift    — the bell, toasts, and deep links
///   • AppState+Polling.swift          — presence heartbeat + badge poll loops
///
/// The task handles below are internal rather than `private` because the
/// polling and observer extensions own them and `didLogout` tears them down.
@Observable
class AppState {
    var isAuthenticated: Bool = false
    /// True from launch until the first `restoreSession()` settles. Without
    /// this there is no third state, so the app rendered the full LoginView —
    /// animated glows and all — for the whole `/auth/refresh` round-trip, then
    /// swapped to the workspace. That flash is what "loads slow" looked like.
    var isRestoring: Bool = true
    var currentUser: UserInfo? = nil
    var selectedThreadId: String? = nil
    var selectedProjectId: String? = nil
    var selectedChannelId: String? = nil
    var selectedJournalId: String? = nil
    /// Selected unread email (id from the Gmail fetch). Routes the primary
    /// detail pane to EmailDetailView. Mutually exclusive with the other
    /// `selected*` ids — set it and clear them (and vice-versa).
    var selectedEmailId: String? = nil
    /// When set, the main window shows a second (pinned) detail pane beside the
    /// primary one — the in-window split. nil = no split. Reuses AuxWindowTarget.
    var splitTarget: AuxWindowTarget? = nil
    /// When set, a third (pinned) detail pane stacks horizontally beneath the
    /// top row — tmux-style: primary + `splitTarget` side by side on top, this
    /// one full-width below. nil = no bottom pane. Reuses AuxWindowTarget; its
    /// header carries a switcher to swap between any of the four surfaces.
    var bottomSplitTarget: AuxWindowTarget? = nil
    /// Cmd+F (or the tab-bar magnifier): shows the find-anything palette —
    /// search every surface + project file, open into main/right/bottom pane,
    /// star to the sidebar. Presented as a sheet by ContentView.
    var showFinderPalette = false
    /// Globally-presented file preview (sidebar file pins, finder palette
    /// "Main Pane" file opens). Presented as a sheet by ContentView.
    var globalPreviewFile: MWProjectFile? = nil
    /// Deep-link hint: when set, the project detail view switches its collab
    /// panel to this tab once it mounts/updates, then clears it. Used by
    /// notification taps so a task notification opens the kanban board.
    var pendingProjectPanel: CollabRightPanel? = nil

    /// Set by "Chat about this ticket" on a kanban card. The project chat
    /// composer picks it up, shows a reply-style reference banner, and weaves
    /// the ticket into the next message it sends. Cleared after send or dismiss.
    var pendingTicketRef: TicketChatRef? = nil

    /// Set when a ticket chip in chat is clicked / "Go to ticket". The kanban
    /// board opens this task's (read-only) viewer once it's loaded, then clears
    /// it. Paired with `pendingProjectPanel = .kanban` to switch to the board.
    var pendingOpenTaskId: String? = nil

    // MARK: - Workspace tabs
    static let maxPinnedTabs = 4
    static let tabsKey = "mw-open-tabs-v1"
    /// Open tabs; Home is always element 0. Persisted across launches.
    var openTabs: [WorkTab] = AppState.loadTabs() {
        didSet { AppState.saveTabs(openTabs) }
    }
    /// The currently-displayed destination (drives tab highlight + what "+" pins).
    var activeTab: WorkTab = .home

    var showSkills: Bool = false
    var showInbox: Bool = false
    var showPeople: Bool = false
    /// Full-pane Archive home (archived projects/threads/journals/channels).
    var showArchive: Bool = false
    var showHome: Bool = false
    /// Full-pane Journals hub — the Obsidian-style parent module that houses all
    /// journals in a folder tree. Reached by clicking the sidebar "Journals"
    /// header. Lowest routing priority (a selected journal opens its detail over
    /// the hub), so it's safe to leave set; explicit nav (home/footer) clears it.
    var showJournalsHub: Bool = false
    /// Full-pane hubs for the other three surfaces — same model as the Journals
    /// hub: the sidebar is nav-only (a row per surface), and clicking a row opens
    /// that surface's dashboard where all items are listed / organized / created.
    /// Lowest routing priority, so a selected item opens its detail over the hub.
    var showProjectsHub: Bool = false
    var showThreadsHub: Bool = false
    var showChannelsHub: Bool = false
    /// Full-pane Productivity hub — personal kanban boards (To Do / In Progress
    /// / Done). Same nav-only model as the other hubs.
    var showProductivityHub: Bool = false
    /// Full-pane "Browse Channels" surface. Reached from the sidebar Channels
    /// section header. Mutually exclusive with thread/project/channel/journal
    /// selection — toggling on clears those.
    var showChannelBrowse: Bool = false

    /// Reset every primary-pane nav flag + selection. Each nav entry point calls
    /// this then sets its ONE destination, so a stale hub/selection can never
    /// mask the new target (Home is the routing `else`, so a lingering
    /// show*Hub would otherwise hide it). Keep in sync with PrimaryDetailPane.
    func clearPrimaryNav() {
        selectedThreadId = nil
        selectedProjectId = nil
        selectedChannelId = nil
        selectedJournalId = nil
        selectedEmailId = nil
        showInbox = false
        showPeople = false
        showArchive = false
        showHome = false
        showSkills = false
        showChannelBrowse = false
        showJournalsHub = false
        showProjectsHub = false
        showThreadsHub = false
        showChannelsHub = false
        showProductivityHub = false
    }

    var onlineUsers: [MWOnlineUser] = []
    var unreadInboxCount: Int = 0
    var notificationsUnreadCount: Int = 0
    var isPlusActive: Bool = false
    var betaFeatures: [String: Bool] = [:]

    // ── Plan entitlements (Free / Lite / Pro / Business) ────────────────
    /// Server-resolved plan + features + quota — single tier read
    /// (GET /matcha-work/entitlements). nil until first fetch; treat nil
    /// as "don't lock anything yet" so a slow fetch never flashes locks.
    var entitlements: MWEntitlements? = nil
    /// Raise the upgrade paywall; `paywallFeature` (optional) selects the
    /// contextual header ("Collab projects need Pro", etc.).
    var showPaywall: Bool = false
    var paywallFeature: String? = nil

    var plan: MWPlan { entitlements?.plan ?? .free }
    /// Gate accessors default OPEN while entitlements are unknown (nil) —
    /// the server enforces regardless; optimistic UI avoids lock flicker.
    private func can(_ feature: String) -> Bool {
        guard let e = entitlements else { return true }
        return e.has(feature)
    }
    var canSoloProjects: Bool { can("projects_solo") }
    var canCollabProjects: Bool { can("projects_collab") }
    var canFullJournals: Bool { can("journals_full") }
    var canEmailAI: Bool { can("email_ai") }
    var canGoLive: Bool { can("go_live") }
    var canPaidChannels: Bool { can("paid_channels") }
    var canProModel: Bool { can("ai_model_pro") }

    /// Raise the paywall for a specific locked feature.
    func presentPaywall(for feature: String?) {
        paywallFeature = feature
        showPaywall = true
    }
    var isSceneActive: Bool = true
    /// Bumped each time the app regains focus (scene active OR
    /// `NSApplication.didBecomeActiveNotification`). The open channel view
    /// observes this to REST-refetch missed messages, since a WS reconnect
    /// replays `join_room` but does not backfill the gap.
    var foregroundTick: Int = 0
    /// Throttle gate for onSceneActive — refocus fires far more often than the
    /// refresh work needs to run.
    var lastSceneActiveAt = Date.distantPast
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
        (UserDefaults.standard.bool(forKey: "mw-chat-theme") ? "light" : "platinum") {
        didSet {
            UserDefaults.standard.set(appTheme, forKey: "mw-theme")
            // Light-family themes drive the chat surfaces into light mode too
            // (ChatPanel / MessageBubble / ThreadDetail read `mw-chat-theme`).
            UserDefaults.standard.set(appTheme == "light" || appTheme == "platinum", forKey: "mw-chat-theme")
        }
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
    /// Server-sourced per-channel unread (seeded by the channels list) so a
    /// channel *tab* can badge without the sidebar's local list in scope.
    var channelUnreadCounts: [String: Int] = [:]
    /// Per-project unread-notification roll-up → werk project tab badge.
    /// Seeded from `/notifications/project-unread-counts`, live-bumped by the
    /// bell observer, and cleared per-entity when the user opens the specific
    /// ticket/note — never on opening the project tab itself.
    var projectUnseenCounts: [String: Int] = [:]

    // Long-lived loops, cancelled on logout. Owned by AppState+Polling.swift
    // and AppState+Notifications.swift.
    var heartbeatTask: Task<Void, Never>?
    var inboxPollTask: Task<Void, Never>?
    var notificationPollTask: Task<Void, Never>?
    var newNotificationTask: Task<Void, Never>?
    var bannerTapTask: Task<Void, Never>?

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
}
