import SwiftUI
import AppKit

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    @State private var threadListVM = ThreadListViewModel()
    @State private var showProfile = false
    // -v2 keys: sections now default-collapsed (clean sidebar — click a header
    // to reveal its items). Bumping the key resets anyone whose old state was
    // persisted open. Starred channels stay pinned-visible even when collapsed.
    @AppStorage("mw-sidebar-channels-open-v2") private var channelsSectionOpen = false
    @AppStorage("mw-sidebar-projects-open-v2") private var projectsSectionOpen = false
    @AppStorage("mw-sidebar-journals-open-v2") private var journalsSectionOpen = false
    @AppStorage("mw-sidebar-threads-open-v2") private var threadsSectionOpen = false
    @AppStorage("mw-sidebar-email-open") private var emailSectionOpen = false
    @State private var showNewJournal = false
    @State private var pendingConnectionsCount = 0
    @State private var showCreateChannel = false
    @State private var showDiscoverChannels = false
    @State private var showNotifications = false
    @State private var orderStore = SidebarSectionOrderStore.shared

    // Search state
    @State private var searchText = ""

    /// Force the sidebar visible on every launch (lands on Home with the
    /// sidebar open). @State re-inits to .all each cold start, so a mid-session
    /// collapse never persists into the next launch.
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        @Bindable var appState = appState

        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebarColumn
        } detail: {
            VStack(spacing: 0) {
                if let bottom = appState.bottomSplitTarget {
                    VSplitView {
                        topPanes
                            .frame(minHeight: 200, maxHeight: .infinity)
                        // 240 min: pane header (~33) + a chat surface's own
                        // header + composer need ~200pt of fixed chrome — any
                        // less and the composer clips off the bottom edge.
                        BottomSplitPane(target: bottom)
                            .frame(minHeight: 240, maxHeight: .infinity)
                    }
                } else {
                    topPanes
                }
            }
            .background(appState.themeBg)
        }
        .environment(appState)
        .tint(appState.themeAccent)
        .background(appState.themeBg)
        // macOS leaves scenePhase `.active` when Werk is merely behind another
        // window, so scenePhase alone never fires onSceneActive on focus regain.
        // didBecomeActive fires whenever Werk becomes frontmost → reconnect the
        // WS + bump foregroundTick so the open channel refetches. connect() is
        // idempotent, so re-firing on every focus is safe.
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            Task { await appState.onSceneActive() }
        }
        .sheet(isPresented: $showProfile) {
            ProfileSheet()
                .environment(appState)
        }
        // Cmd+F find-anything palette (tab bar moved into the sidebar; Cmd+F is the entry point).
        .sheet(isPresented: $appState.showFinderPalette) {
            SplitFinderPalette()
                .environment(appState)
        }
        // Upgrade paywall — raised by any locked surface via presentPaywall(for:).
        .sheet(isPresented: $appState.showPaywall, onDismiss: { appState.paywallFeature = nil }) {
            PaywallSheet()
                .environment(appState)
        }
        // Shared file preview — raised by sidebar file pins and the finder
        // palette's "Main Pane" file opens.
        .sheet(item: $appState.globalPreviewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
        .alert("Enable notifications?", isPresented: $appState.showNotificationReprompt) {
            Button("Open Settings") {
                ChannelNotificationManager.shared.openSystemNotificationSettings()
            }
            Button("Don't ask again", role: .destructive) {
                ChannelNotificationManager.shared.promptSuppressed = true
            }
            Button("Not now", role: .cancel) { }
        } message: {
            Text("Notifications are off. Turn them on in System Settings → Notifications → Matcha so you don't miss channel mentions, task assignments, and project updates.")
        }
        .sheet(isPresented: $showCreateChannel) {
            CreateChannelSheet { newChannel in
                appState.selectedThreadId = nil
                appState.selectedProjectId = nil
                appState.selectedJournalId = nil
                appState.channelsListGeneration &+= 1
                NotificationCenter.default.post(name: .mwChannelCreated, object: newChannel.id)
            }
        }
        .sheet(isPresented: $showDiscoverChannels) {
            DiscoverChannelsSheet { joinedId in
                appState.channelsListGeneration &+= 1
                appState.selectedChannelId = joinedId
                appState.selectedThreadId = nil
                appState.selectedProjectId = nil
                appState.selectedJournalId = nil
            }
        }
        .sheet(isPresented: $appState.showChannelAdminWizard, onDismiss: {
            // Latch the "seen" flag on every dismissal route — Esc, click-out,
            // explicit Close button. Skipping this here lets the auto-show
            // re-fire on the next channels reload.
            UserDefaults.standard.set(true, forKey: "channel-admin-wizard-shown-v1")
        }) {
            ChannelAdminWizardView(mode: appState.channelAdminWizardMode)
        }
        .sheet(isPresented: $appState.showCollabProjectWizard, onDismiss: {
            UserDefaults.standard.set(true, forKey: "collab-project-wizard-shown-v1")
        }) {
            CollabProjectWizardView(mode: appState.collabProjectWizardMode)
        }
        .overlay(alignment: .topTrailing) {
            // In-app toast banner for inbound channel messages. Stacks
            // up to 3, auto-dismisses each after 5s, tap to switch to
            // the channel. Sits above all view content via .overlay so
            // it doesn't push the layout around.
            ChannelToastOverlay()
        }
        .overlay(alignment: .bottomTrailing) {
            // In-app toast for collaborator kanban/ticket changes. Bottom-right
            // so it doesn't collide with channel toasts (top-right). Tap to
            // jump to the project board.
            WorkToastOverlay()
        }
        .toolbar {
            ToolbarItem(placement: .status) {
                if let user = appState.currentUser {
                    HStack(spacing: 10) {
                        Button {
                            showNotifications.toggle()
                        } label: {
                            NotificationBellBadge()
                        }
                        .buttonStyle(.plain)
                        .help("Notifications")
                        .popover(isPresented: $showNotifications) {
                            NotificationsPopoverView()
                                .environment(appState)
                        }
                        Button {
                            showProfile = true
                        } label: {
                            // Business accounts show their company name; personal
                            // (and other) accounts fall back to email.
                            Text(user.companyName ?? user.email)
                                .font(.system(size: 12))
                                .foregroundColor(appState.themeText.opacity(0.55))
                                .underline(false)
                        }
                        .buttonStyle(.plain)
                        .help("Edit profile")
                        // Plan badge — free/lite open the paywall; pro/business
                        // open it too (it renders "Current plan" states).
                        Button {
                            appState.presentPaywall(for: nil)
                        } label: {
                            Text(appState.plan == .free ? "upgrade" : appState.plan.displayName.lowercased())
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color.matcha500)
                        }
                        .buttonStyle(.plain)
                        .help(appState.plan == .free ? "Upgrade Werk" : "Werk \(appState.plan.displayName) — view plans")
                        Button("logout") {
                            Task {
                                try? await AuthService.shared.logout()
                                await MainActor.run { appState.didLogout() }
                            }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.5))
                    }
                }
            }
        }
    }

    // MARK: - Top split row

    /// The top region of the detail area: primary pane alone, or primary +
    /// secondary side by side when `splitTarget` is set. Pulled out so it can
    /// nest inside the outer VSplitView once a bottom pane is open.
    @ViewBuilder
    private var topPanes: some View {
        if let split = appState.splitTarget {
            HSplitView {
                PrimaryDetailPane()
                    .frame(minWidth: 360, maxWidth: .infinity, maxHeight: .infinity)
                SplitSecondaryPane(target: split)
                    .frame(minWidth: 360, maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            PrimaryDetailPane()
        }
    }

    // MARK: - Sidebar column

    @ViewBuilder
    private var sidebarColumn: some View {
        VStack(spacing: 0) {
            // Brand header — MW monogram + wordmark, pinned above the scroll.
            HStack(spacing: 9) {
                MWMonogram(size: 26)
                Text("Matcha Work")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(appState.themeText)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 14)
            .padding(.top, 12)
            .padding(.bottom, 8)

            ScrollView {
                VStack(spacing: 0) {
                    sidebarHomeButton
                    sidebarSearchBar
                    WorkTabsSidebarSection()
                    SidebarStarredView()
                    sidebarOrderedSections
                }
            }

            Divider().background(appState.themeBorder)

            // Footer — Inbox + People always-visible buttons with live badges
            HStack(spacing: 6) {
                InboxFooterButton {
                    appState.clearPrimaryNav()
                    appState.showInbox = true
                }

                sidebarFooterButton(
                    icon: "person.2",
                    label: "People",
                    badge: pendingConnectionsCount,
                    isActive: appState.showPeople
                ) {
                    appState.clearPrimaryNav()
                    appState.showPeople = true
                }

                sidebarFooterButton(
                    icon: "archivebox",
                    label: "Archive",
                    badge: 0,
                    isActive: appState.showArchive
                ) {
                    appState.clearPrimaryNav()
                    appState.showArchive = true
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
        }
        .background(sidebarBackground)
        .navigationSplitViewColumnWidth(min: 260, ideal: 300, max: 380)
        .task {
            await refreshPendingConnections()
        }
    }

    @ViewBuilder
    private var sidebarHomeButton: some View {
        let isHomeActive = !appState.showJournalsHub && !appState.showProjectsHub
            && !appState.showThreadsHub && !appState.showChannelsHub && (appState.showHome || (
            appState.selectedThreadId == nil &&
            appState.selectedProjectId == nil &&
            appState.selectedChannelId == nil &&
            appState.selectedJournalId == nil &&
            appState.selectedEmailId == nil &&
            !appState.showInbox &&
            !appState.showPeople &&
            !appState.showSkills &&
            !appState.showChannelBrowse
        ))
        sidebarFooterButton(icon: "house", label: "Home", badge: 0, isActive: isHomeActive) {
            appState.clearPrimaryNav()
            appState.showHome = true
        }
        .padding(.horizontal, 8)
        .padding(.top, 8)
        .padding(.bottom, 4)
    }

    @ViewBuilder
    private var sidebarSearchBar: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundColor(appState.themeTextSecondary)
                .font(.system(size: 11))
            TextField("Filter sidebar...", text: $searchText)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
            if !searchText.isEmpty {
                Button {
                    searchText = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(appState.themeTextSecondary)
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(appState.themeCard.opacity(appState.isLightFamily ? 0.8 : 0.4))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(appState.themeBorder, lineWidth: 1)
        )
        .padding(.horizontal, 8)
        .padding(.bottom, 8)
    }

    @ViewBuilder
    private var sidebarOrderedSections: some View {
        let _ = orderStore.generation
        // All sections always visible — locked ones (by plan) render a lock
        // affordance that raises the paywall instead of hiding (conversion).
        // The old admin-set beta-flag filter is folded into the server-resolved
        // plan (beta_full → pro-equivalent, beta_lite → lite-equivalent).
        let visibleSections = orderStore.order
        ForEach(Array(visibleSections.enumerated()), id: \.element) { idx, section in
            sidebarSectionView(for: section)
                .draggable(section.rawValue) {
                    sectionDragPreview(section)
                }
                .dropDestination(for: String.self) { items, _ in
                    guard let raw = items.first,
                          let dragged = SidebarSectionOrderStore.Section(rawValue: raw),
                          dragged != section else {
                        return false
                    }
                    orderStore.move(dragged, before: section)
                    return true
                }
                .contextMenu {
                    Button("Move up") { orderStore.moveUp(section) }
                        .disabled(idx == 0)
                    Button("Move down") { orderStore.moveDown(section) }
                        .disabled(idx == visibleSections.count - 1)
                    Divider()
                    Button("Reset sidebar order") {
                        orderStore.resetToDefault()
                    }
                }
            if idx < visibleSections.count - 1 {
                Divider().background(appState.themeBorder)
            }
        }
    }

    // MARK: - Sidebar sections (drag-droppable)

    @ViewBuilder
    private func sidebarSectionView(for section: SidebarSectionOrderStore.Section) -> some View {
        switch section {
        case .channels: channelsSidebarSection
        case .projects: projectsSidebarSection
        case .journals: journalsSidebarSection
        case .productivity: productivitySidebarSection
        case .threads:  threadsSidebarSection
        case .email:    emailSidebarSection
        }
    }

    private func sectionDragPreview(_ section: SidebarSectionOrderStore.Section) -> some View {
        HStack(spacing: 6) {
            Image(systemName: section.iconName)
                .font(.system(size: 11))
            Text(section.displayName)
                .font(.system(size: 12, weight: .semibold))
        }
        .foregroundColor(.white)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.zinc800)
        .cornerRadius(6)
    }

    /// A single nav-only sidebar row: clicking the label opens that surface's
    /// full-pane hub; the optional trailing slot carries a create "+" control.
    /// The sidebar lists NO individual items — browsing/organizing lives in the
    /// hub (only the Starred pins strip surfaces specific items).
    @ViewBuilder
    private func sidebarNavRow<Trailing: View>(
        title: String, icon: String, isActive: Bool,
        // When set, the row renders a lock and opens the paywall (with this
        // feature key) instead of navigating. nil = unlocked.
        lockedFeature: String? = nil,
        onOpen: @escaping () -> Void,
        @ViewBuilder trailing: () -> Trailing = { EmptyView() }
    ) -> some View {
        HStack(spacing: 6) {
            Button(action: {
                if let feature = lockedFeature {
                    appState.presentPaywall(for: feature)
                } else {
                    onOpen()
                }
            }) {
                HStack(spacing: 8) {
                    Image(systemName: icon)
                        .font(.system(size: 12))
                        .foregroundColor(isActive ? appState.themeAccent : appState.themeTextSecondary)
                        .frame(width: 16)
                    Text(title.uppercased())
                        .font(.system(size: 10, weight: .semibold))
                        .tracking(0.5)
                        .foregroundColor(isActive ? appState.themeAccent : appState.themeTextSecondary)
                    if lockedFeature != nil {
                        Image(systemName: "lock.fill")
                            .font(.system(size: 8))
                            .foregroundColor(appState.themeTextSecondary.opacity(0.7))
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            trailing()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isActive ? appState.themeAccent.opacity(0.12) : Color.clear)
        )
    }

    /// Small "+" chip reused by the section create controls.
    private var plusChip: some View {
        Image(systemName: "plus")
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(.secondary)
            .frame(width: 18, height: 18)
            .background(Color(white: 0.58))
            .cornerRadius(4)
    }

    @ViewBuilder
    private var channelsSidebarSection: some View {
        sidebarNavRow(title: "Channels", icon: "number",
                      isActive: appState.showChannelsHub, onOpen: openChannelsHub) {
            Menu {
                Button("New channel") {
                    appState.channelAdminWizardMode = .create
                    appState.showChannelAdminWizard = true
                }
                Button("Quick create (no guide)") { showCreateChannel = true }
                Divider()
                Button("Browse public channels") { showChannelBrowse() }
            } label: {
                plusChip
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .frame(width: 22, height: 18)
            .help("New channel · browse")
        }
    }

    @ViewBuilder
    private var projectsSidebarSection: some View {
        // No "+" here — project creation lives on the Projects home page
        // (ProjectsLibraryView), not as a sidebar shortcut.
        sidebarNavRow(title: "Projects", icon: "folder",
                      isActive: appState.showProjectsHub,
                      lockedFeature: appState.canSoloProjects ? nil : "projects_solo",
                      onOpen: openProjectsHub)
    }

    /// Open the Journals hub — the Obsidian-style parent module that houses all
    /// journals in a folder tree. Clears the other nav surfaces so the hub takes
    /// the primary pane.
    private func openJournalsHub()  { appState.clearPrimaryNav(); appState.showJournalsHub = true }
    private func openProjectsHub()  { appState.clearPrimaryNav(); appState.showProjectsHub = true }
    private func openThreadsHub()   { appState.clearPrimaryNav(); appState.showThreadsHub = true }
    private func openChannelsHub()  { appState.clearPrimaryNav(); appState.showChannelsHub = true }
    private func openProductivityHub() { appState.clearPrimaryNav(); appState.showProductivityHub = true }

    /// Nav-only row — opens the full-pane Notes-style Journals workspace
    /// (folders · note list · editor). Browsing/organizing lives in the
    /// workspace, not the sidebar.
    @ViewBuilder
    private var journalsSidebarSection: some View {
        sidebarNavRow(title: "Journals", icon: "book.closed",
                      isActive: appState.showJournalsHub, onOpen: openJournalsHub) {
            Button { openJournalsHub() } label: { plusChip }
                .buttonStyle(.plain)
                .help("Open Journals")
        }
    }

    /// Nav-only row — opens the Productivity hub (personal kanban boards).
    @ViewBuilder
    private var productivitySidebarSection: some View {
        sidebarNavRow(title: "Productivity", icon: "checklist",
                      isActive: appState.showProductivityHub, onOpen: openProductivityHub) {
            Button { openProductivityHub() } label: { plusChip }
                .buttonStyle(.plain)
                .help("Open Productivity")
        }
    }


    @ViewBuilder
    private var threadsSidebarSection: some View {
        sidebarNavRow(title: "Threads", icon: "bubble.left.and.bubble.right",
                      isActive: appState.showThreadsHub, onOpen: openThreadsHub) {
            Button { createThreadFromSidebar() } label: { plusChip }
                .buttonStyle(.plain)
                .help("New thread")
        }
    }

    /// Create a thread straight from the sidebar "+" and open it (the inline
    /// list that used to handle `.mwCreateNewThread` is gone — the Threads hub
    /// owns browsing now).
    private func createThreadFromSidebar() {
        Task {
            if let t = await threadListVM.createThread(title: nil) {
                await MainActor.run {
                    appState.clearPrimaryNav()
                    appState.selectedThreadId = t.id
                }
            }
        }
    }

    @ViewBuilder
    private var emailSidebarSection: some View {
        sidebarSection(
            title: "Email",
            icon: "envelope",
            isOpen: $emailSectionOpen,
            trailing: {
                Button {
                    Task { await EmailViewModel.shared.loadInbox() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.secondary)
                        .frame(width: 18, height: 18)
                        .background(Color(white: 0.58))
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .help("Refresh unread")
            }
        ) {
            EmailSidebarView(searchText: searchText)
        }
    }

    private func setThreadFilter(_ status: String?) {
        threadListVM.filterStatus = status
        Task { await threadListVM.loadThreads() }
    }

    // MARK: - Sidebar building blocks

    /// The primary (left) detail pane — routed off the shared `selectedX`
    /// nav state. The detail panes live in DetailPanes.swift (PrimaryDetailPane /
    /// SplitSecondaryPane) so churning unread counters don't rebuild them.

    /// Navigate to the full-pane Channels browse view. Clears any active
    /// thread/project/channel/journal/inbox selection so the detail pane
    /// renders the browse surface unambiguously.
    private func showChannelBrowse() {
        appState.showChannelBrowse = true
        appState.selectedThreadId = nil
        appState.selectedProjectId = nil
        appState.selectedChannelId = nil
        appState.selectedJournalId = nil
        appState.selectedEmailId = nil
        appState.showInbox = false
        appState.showPeople = false
        appState.showSkills = false
        appState.showHome = false
    }

    private func sidebarSection<Content: View, Trailing: View>(
        title: String,
        icon: String,
        isOpen: Binding<Bool>,
        // When true the content always renders (collapsed or not) and decides
        // for itself what to show while collapsed — used by Channels to keep
        // starred channels pinned-visible. Other sections hide content when shut.
        alwaysRenderContent: Bool = false,
        @ViewBuilder trailing: () -> Trailing = { EmptyView() },
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Button {
                    withAnimation(.easeOut(duration: 0.15)) { isOpen.wrappedValue.toggle() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: isOpen.wrappedValue ? "chevron.down" : "chevron.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                            .frame(width: 10)
                        Image(systemName: icon)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text(title.uppercased())
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.secondary)
                            .tracking(0.5)
                        Spacer()
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                trailing()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            if isOpen.wrappedValue || alwaysRenderContent {
                content()
            }
        }
    }

    @ViewBuilder
    private func sidebarFooterButton(
        icon: String,
        label: String,
        badge: Int,
        isActive: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(isActive ? appState.themeAccent : appState.themeTextSecondary)
                Text(label)
                    .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                    .foregroundColor(isActive ? appState.themeAccent : appState.themeText.opacity(0.85))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                if badge > 0 {
                    Text("\(badge)")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeAccent)
                        .clipShape(Capsule())
                }
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive ? appState.themeAccent.opacity(0.14) : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }

    private func refreshPendingConnections() async {
        do {
            let list = try await ChannelsService.shared.listPendingConnections()
            await MainActor.run { pendingConnectionsCount = list.count }
        } catch {
            // Silent failure — badge just won't update
        }
    }

    // Checkout moved into PaywallSheet (per-plan Lite/Pro buttons).

    // MARK: - Starred section & theme background helpers

    /// Tint strength layered over the sidebar vibrancy. Cappuchin needs the
    /// most (neutral frost → warm espresso); dark the least (let vibrancy read).
    private var sidebarTintOpacity: Double {
        switch appState.appTheme {
        case "cappuchin": return 0.72
        case "light": return 0.55
        case "platinum": return 0.55
        default: return 0.40
        }
    }

    @ViewBuilder
    private var sidebarBackground: some View {
        if #available(macOS 26.0, *) {
            // Liquid Glass: system glass, tinted to the (contrasting) sidebar color.
            Rectangle()
                .fill(appState.themeSidebar.opacity(sidebarTintOpacity * 0.5))
                .glassEffect(.regular.tint(appState.themeSidebar.opacity(0.28)), in: Rectangle())
        } else {
            // macOS 14/15 can't render Liquid Glass and `.behindWindow` vibrancy
            // samples the desktop wallpaper — at partial tint opacity that washed
            // the intended contrast out. Render the SOLID contrasting color so the
            // rail always separates from the opaque body: lighter than the
            // dark/cappuchin bg, darker than the light bg.
            appState.themeSidebar
        }
    }

}
