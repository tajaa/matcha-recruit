import SwiftUI
import AppKit

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @State private var threadListVM = ThreadListViewModel()
    @State private var isOpeningCheckout = false
    @State private var upgradeError: String?
    @State private var showProfile = false
    @AppStorage("mw-sidebar-channels-open") private var channelsSectionOpen = false
    @AppStorage("mw-sidebar-projects-open") private var projectsSectionOpen = false
    @AppStorage("mw-sidebar-journals-open") private var journalsSectionOpen = false
    @AppStorage("mw-sidebar-threads-open") private var threadsSectionOpen = false
    @AppStorage("mw-sidebar-email-open") private var emailSectionOpen = false
    @State private var showNewJournal = false
    @State private var showNewBlog = false
    @State private var pendingConnectionsCount = 0
    @State private var showCreateChannel = false
    @State private var showDiscoverChannels = false
    @State private var showProjectTypePicker = false
    @State private var isCreatingProject = false
    @State private var projectCreateError: String?
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
                WorkTabBar()
                if let bottom = appState.bottomSplitTarget {
                    VSplitView {
                        topPanes
                            .frame(minHeight: 200, maxHeight: .infinity)
                        BottomSplitPane(target: bottom)
                            .frame(minHeight: 160, maxHeight: .infinity)
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
                        if !appState.isPlusActive {
                            Button {
                                startUpgrade()
                            } label: {
                                Text(isOpeningCheckout ? "opening…" : "upgrade")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(upgradeError == nil ? Color.matcha500 : .red.opacity(0.8))
                            }
                            .buttonStyle(.plain)
                            .disabled(isOpeningCheckout)
                            .help(upgradeError ?? "Upgrade to Matcha Plus")
                        } else {
                            Text("plus")
                                .font(.system(size: 11))
                                .foregroundColor(Color.matcha500.opacity(0.8))
                        }
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
            ScrollView {
                VStack(spacing: 0) {
                    sidebarHomeButton
                    sidebarSearchBar
                    sidebarOrderedSections
                }
            }

            Divider().background(appState.themeBorder)

            // Footer — Inbox + People always-visible buttons with live badges
            HStack(spacing: 6) {
                InboxFooterButton {
                    appState.showInbox = true
                    appState.selectedEmailId = nil
                    appState.showPeople = false
                    appState.showHome = false
                    appState.showChannelBrowse = false
                    appState.showArchive = false
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
                    appState.showSkills = false
                }

                sidebarFooterButton(
                    icon: "person.2",
                    label: "People",
                    badge: pendingConnectionsCount,
                    isActive: appState.showPeople
                ) {
                    appState.showPeople = true
                    appState.selectedEmailId = nil
                    appState.showInbox = false
                    appState.showHome = false
                    appState.showChannelBrowse = false
                    appState.showArchive = false
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
                    appState.showSkills = false
                }

                sidebarFooterButton(
                    icon: "archivebox",
                    label: "Archive",
                    badge: 0,
                    isActive: appState.showArchive
                ) {
                    appState.showArchive = true
                    appState.selectedEmailId = nil
                    appState.showInbox = false
                    appState.showPeople = false
                    appState.showHome = false
                    appState.showChannelBrowse = false
                    appState.showSkills = false
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
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
        let isHomeActive = appState.showHome || (
            appState.selectedThreadId == nil &&
            appState.selectedProjectId == nil &&
            appState.selectedChannelId == nil &&
            appState.selectedEmailId == nil &&
            !appState.showInbox &&
            !appState.showPeople &&
            !appState.showSkills &&
            !appState.showChannelBrowse
        )
        sidebarFooterButton(icon: "house", label: "Home", badge: 0, isActive: isHomeActive) {
            appState.showHome = true
            appState.selectedEmailId = nil
            appState.showInbox = false
            appState.showPeople = false
            appState.showSkills = false
            appState.showChannelBrowse = false
            appState.selectedThreadId = nil
            appState.selectedProjectId = nil
            appState.selectedChannelId = nil
            appState.selectedJournalId = nil
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
                .fill(appState.themeCard.opacity(appState.appTheme == "light" ? 0.8 : 0.4))
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
        let visibleSections = orderStore.order.filter { section in
            switch section {
            case .projects, .journals: return appState.mwBetaLite
            default: return true
            }
        }
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

    @ViewBuilder
    private var channelsSidebarSection: some View {
        sidebarSection(
            title: "Channels",
            icon: "number",
            isOpen: $channelsSectionOpen,
            trailing: {
                HStack(spacing: 4) {
                    Button {
                        showChannelBrowse()
                    } label: {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.secondary)
                            .frame(width: 18, height: 18)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("Browse public channels")

                    Menu {
                        Button("New channel") {
                            appState.channelAdminWizardMode = .create
                            appState.showChannelAdminWizard = true
                        }
                        Button("Quick create (no guide)") {
                            showCreateChannel = true
                        }
                        Divider()
                        Button("Browse public channels") {
                            showChannelBrowse()
                        }
                        Divider()
                        Button("Channel admin guide") {
                            if let id = appState.selectedChannelId {
                                appState.channelAdminWizardMode = .manage(channelId: id)
                            } else {
                                appState.channelAdminWizardMode = .create
                            }
                            appState.showChannelAdminWizard = true
                        }
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.secondary)
                            .frame(width: 18, height: 18)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .frame(width: 22, height: 18)
                    .help("New channel · admin guide")
                }
            }
        ) {
            ChannelsSidebarView(showHeader: false, searchText: searchText)
        }
    }

    @ViewBuilder
    private var projectsSidebarSection: some View {
        sidebarSection(
            title: "Projects",
            icon: "folder",
            isOpen: $projectsSectionOpen,
            trailing: {
                Button { showProjectTypePicker = true } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.secondary)
                        .frame(width: 18, height: 18)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .help("New project")
                .disabled(isCreatingProject)
                .popover(isPresented: $showProjectTypePicker) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("New Project").font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
                            .padding(.bottom, 4)
                        ForEach(["general", "presentation", "recruiting", "collab"], id: \.self) { type in
                            Button {
                                showProjectTypePicker = false
                                if type == "collab" {
                                    appState.collabProjectWizardMode = .create
                                    appState.showCollabProjectWizard = true
                                } else {
                                    createProject(type: type)
                                }
                            } label: {
                                HStack {
                                    Image(systemName: iconForProjectType(type))
                                        .font(.system(size: 11))
                                        .frame(width: 16)
                                    Text(labelForProjectType(type))
                                        .font(.system(size: 12))
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 4)
                            }
                            .buttonStyle(.plain)
                            .foregroundColor(.white)
                        }
                        Button {
                            showProjectTypePicker = false
                            showNewBlog = true
                        } label: {
                            HStack {
                                Image(systemName: "doc.richtext")
                                    .font(.system(size: 11))
                                    .frame(width: 16)
                                Text("Blog Post")
                                    .font(.system(size: 12))
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 4)
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(.white)
                    }
                    .padding(12)
                    .frame(width: 180)
                }
                .sheet(isPresented: $showNewBlog) {
                    NewBlogSheet { proj in
                        appState.selectedProjectId = proj.id
                        appState.selectedThreadId = nil
                        appState.selectedChannelId = nil
                        appState.selectedJournalId = nil
                        appState.projectsListGeneration &+= 1
                    }
                }
            }
        ) {
            VStack(alignment: .leading, spacing: 0) {
                if let err = projectCreateError {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 9))
                            .foregroundColor(.red)
                        Text(err)
                            .font(.system(size: 10))
                            .foregroundColor(.red)
                            .lineLimit(3)
                        Spacer()
                        Button { projectCreateError = nil } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 8))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.red.opacity(0.1))
                }
                ProjectListView(showHeader: false, searchText: searchText)
            }
        }
    }

    @ViewBuilder
    private var journalsSidebarSection: some View {
        sidebarSection(
            title: "Journals",
            icon: "book.closed",
            isOpen: $journalsSectionOpen,
            trailing: {
                Button { showNewJournal = true } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.secondary)
                        .frame(width: 18, height: 18)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .help("New journal")
                .sheet(isPresented: $showNewJournal) {
                    NewJournalSheet { journal in
                        appState.selectedJournalId = journal.id
                        appState.selectedThreadId = nil
                        appState.selectedProjectId = nil
                        appState.selectedChannelId = nil
                        appState.journalsListGeneration &+= 1
                    }
                }
            }
        ) {
            JournalListView(showHeader: false, searchText: searchText)
        }
    }

    @ViewBuilder
    private var threadsSidebarSection: some View {
        sidebarSection(
            title: "Threads",
            icon: "bubble.left.and.bubble.right",
            isOpen: $threadsSectionOpen,
            trailing: {
                HStack(spacing: 4) {
                    Menu {
                        Button("All") { setThreadFilter(nil) }
                        Button("Active") { setThreadFilter("active") }
                        Button("Finalized") { setThreadFilter("finalized") }
                    } label: {
                        Image(systemName: "line.3.horizontal.decrease.circle")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(threadListVM.filterStatus == nil ? .secondary : appState.themeAccent)
                            .frame(width: 18, height: 18)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()
                    .help("Filter threads")

                    Button {
                        NotificationCenter.default.post(name: .mwCreateNewThread, object: nil)
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.secondary)
                            .frame(width: 18, height: 18)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("New thread")
                }
            }
        ) {
            ThreadListView(viewModel: threadListVM, showHeader: false, searchText: searchText)
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
                        .background(Color.zinc800)
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

            if isOpen.wrappedValue {
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

    private func createProject(type: String) {
        isCreatingProject = true
        projectCreateError = nil
        Task {
            do {
                let proj = try await MatchaWorkService.shared.createProject(title: "New Project", projectType: type)
                await MainActor.run {
                    appState.selectedProjectId = proj.id
                    appState.selectedThreadId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
                    appState.projectsListGeneration &+= 1
                    isCreatingProject = false
                }
            } catch {
                await MainActor.run {
                    isCreatingProject = false
                    projectCreateError = "Couldn't create project: \(error.localizedDescription)"
                }
            }
        }
    }

    private func iconForProjectType(_ type: String) -> String {
        switch type {
        case "general": return "doc.text"
        case "presentation": return "rectangle.on.rectangle"
        case "recruiting": return "person.3"
        case "collab": return "person.2.crop.square.stack"
        default: return "doc.text"
        }
    }

    private func labelForProjectType(_ type: String) -> String {
        switch type {
        case "collab": return "Collab"
        default: return type.capitalized
        }
    }

    @MainActor
    private func startUpgrade() {
        guard !isOpeningCheckout else { return }
        isOpeningCheckout = true
        upgradeError = nil
        Task { @MainActor in
            defer { isOpeningCheckout = false }
            do {
                let urlString = try await MatchaWorkService.shared.startPersonalCheckout(
                    successUrl: "https://hey-matcha.com/work?upgraded=1",
                    cancelUrl: "https://hey-matcha.com/work?canceled=1"
                )
                guard let checkoutURL = URL(string: urlString) else {
                    upgradeError = "invalid checkout URL from server"
                    return
                }
                NSWorkspace.shared.open(checkoutURL)
                // Subscription refresh happens when the user returns to the app
                // via the scenePhase .active observer in MatchaApp.
            } catch {
                upgradeError = error.localizedDescription
            }
        }
    }

    // MARK: - Starred section & theme background helpers

    /// Tint strength layered over the sidebar vibrancy. Cappuchin needs the
    /// most (neutral frost → warm espresso); dark the least (let vibrancy read).
    private var sidebarTintOpacity: Double {
        switch appState.appTheme {
        case "cappuchin": return 0.72
        case "light": return 0.55
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

// MARK: - Mac Native Visual Effect View

struct VisualEffectView: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode = .behindWindow

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}

// MARK: - Glass panels (Liquid Glass on macOS 26, vibrancy material on 14/15)

/// A premium translucent floating surface. On macOS 26+ it renders true
/// Liquid Glass via `glassEffect`; on macOS 14/15 it falls back to a tinted
/// `NSVisualEffectView` material so it still looks frosted today. The theme
/// `tint` (layered over the frost) keeps each theme's identity and preserves
/// text contrast — the old full-window `.ultraThinMaterial` washout is avoided
/// by scoping this to discrete chrome / floating surfaces only.
struct GlassPanelModifier: ViewModifier {
    var cornerRadius: CGFloat = 12
    var material: NSVisualEffectView.Material = .menu
    var blending: NSVisualEffectView.BlendingMode = .withinWindow
    var tint: Color
    var tintOpacity: Double = 0.5
    var stroke: Color = .white.opacity(0.10)
    var shadow: Bool = true

    @ViewBuilder
    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        if #available(macOS 26.0, *) {
            content
                .glassEffect(.regular.tint(tint.opacity(min(tintOpacity, 0.35))), in: shape)
        } else {
            content
                .background {
                    ZStack {
                        VisualEffectView(material: material, blendingMode: blending)
                        tint.opacity(tintOpacity)
                    }
                    .clipShape(shape)
                }
                .overlay(shape.stroke(stroke, lineWidth: 1))
                .shadow(color: shadow ? .black.opacity(0.20) : .clear,
                        radius: shadow ? 14 : 0, y: shadow ? 6 : 0)
        }
    }
}

extension View {
    /// Frosted floating panel — see `GlassPanelModifier`.
    func glassPanel(
        cornerRadius: CGFloat = 12,
        material: NSVisualEffectView.Material = .menu,
        blending: NSVisualEffectView.BlendingMode = .withinWindow,
        tint: Color,
        tintOpacity: Double = 0.5,
        stroke: Color = .white.opacity(0.10),
        shadow: Bool = true
    ) -> some View {
        modifier(GlassPanelModifier(
            cornerRadius: cornerRadius, material: material, blending: blending,
            tint: tint, tintOpacity: tintOpacity, stroke: stroke, shadow: shadow))
    }
}

// MARK: - Muted radial background

/// A soft, top-anchored radial grayscale gradient used behind content panes
/// (Home, collab). Center is a hair lighter than the flat theme bg, edges a
/// hair darker — quiet depth, no color. This is the "muted elegance" base the
/// elevated cards float on.
struct ThemeRadialBackground: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        let pair: (Color, Color)
        switch appState.appTheme {
        case "light":     pair = (.grayRadialCenter, .grayRadialEdge)
        case "cappuchin": pair = (.cappuchinRadialCenter, .cappuchinRadialEdge)
        case "graphite":  pair = (.graphiteRadialCenter, .graphiteRadialEdge)
        default:          pair = (.darkRadialCenter, .darkRadialEdge)
        }
        return RadialGradient(
            gradient: Gradient(colors: [pair.0, pair.1]),
            center: .top,
            startRadius: 0,
            endRadius: 1100
        )
        .ignoresSafeArea()
    }
}

// MARK: - Elevated card (depth for light mode; border for dark)

/// Premium card surface. In light mode it floats on soft layered shadows with
/// no harsh border (Linear/Things aesthetic); in dark/cappuchin, where black
/// shadows don't read, it uses a crisp hairline border plus a faint shadow.
/// This is what carries "premium" on macOS 15, where glass can't blur an
/// opaque content pane.
struct ElevatedCardModifier: ViewModifier {
    var cornerRadius: CGFloat = 12
    @Environment(AppState.self) private var appState

    func body(content: Content) -> some View {
        let isLight = appState.appTheme == "light"
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return content
            .background(shape.fill(Color.cardBackground))
            .overlay(shape.strokeBorder(appState.themeBorder.opacity(isLight ? 0.0 : 0.9), lineWidth: 1))
            // Two-layer shadow: a soft ambient spread + a tight contact shadow.
            .shadow(color: .black.opacity(isLight ? 0.08 : 0.0), radius: 16, y: 5)
            .shadow(color: .black.opacity(isLight ? 0.06 : 0.22), radius: 2, y: 1)
    }
}

extension View {
    func elevatedCard(cornerRadius: CGFloat = 12) -> some View {
        modifier(ElevatedCardModifier(cornerRadius: cornerRadius))
    }
}

/// Tab strip above the detail pane. Home is permanent (element 0); up to
/// `AppState.maxPinnedTabs` pinned items sit beside it. Click a tab to switch,
/// "×" to close, "+" to pin the currently-open item.
struct WorkTabBar: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        HStack(spacing: 4) {
            ForEach(appState.openTabs) { tab in
                tabChip(tab)
            }
            Button { appState.pinActiveTab() } label: {
                Image(systemName: "plus")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                    .frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(!appState.canPinActiveTab)
            .opacity(appState.canPinActiveTab ? 1 : 0.3)
            .help(pinHelp)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(appState.themeBg)
        .overlay(alignment: .bottom) { Divider().opacity(0.4) }
    }

    private var pinHelp: String {
        if appState.activeTab.kind == .home { return "Home is always open" }
        if appState.openTabs.contains(where: { $0.id == appState.activeTab.id }) { return "Already pinned" }
        if appState.pinnedTabCount >= AppState.maxPinnedTabs { return "Tab limit reached" }
        return "Pin “\(appState.activeTab.title)” as a tab"
    }

    private func tabChip(_ tab: WorkTab) -> some View {
        let active = appState.activeTab.id == tab.id
        let unseen = appState.tabUnread(tab)
        return HStack(spacing: 6) {
            Image(systemName: tab.icon).font(.system(size: 10))
            Text(tab.title)
                .font(.system(size: 12, weight: active ? .semibold : .regular))
                .lineLimit(1)
                .truncationMode(.tail)
            if unseen > 0 {
                Text(unseen > 10 ? "10+" : "\(unseen)")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(appState.themeAccent))
            }
            if tab.kind != .home {
                Button { appState.closeTab(tab) } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundColor(appState.themeText.opacity(0.5))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help("Close tab")
            }
        }
        .foregroundColor(active ? appState.themeText : appState.themeText.opacity(0.6))
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .frame(maxWidth: 170)
        .background(
            RoundedRectangle(cornerRadius: 7)
                .fill(active ? appState.themeAccent.opacity(0.14) : Color.clear)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .stroke(active ? appState.themeAccent.opacity(0.3) : appState.themeBorder.opacity(0.45), lineWidth: 1)
        )
        .contentShape(Rectangle())
        .onTapGesture { appState.selectTab(tab) }
    }
}

/// "Show N more" row used by sidebar lists that paginate (projects, channels,
/// journals, threads) so the sidebar stays short. Reveals the next batch.
struct SidebarShowMoreButton: View {
    @Environment(AppState.self) private var appState
    let remaining: Int
    let pageSize: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold))
                Text("Show \(min(pageSize, remaining)) more").font(.system(size: 10, weight: .medium))
                Spacer()
            }
            .foregroundColor(appState.themeTextSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("\(remaining) more")
    }
}

struct SidebarRowModifier: ViewModifier {
    let isSelected: Bool
    @Environment(AppState.self) private var appState
    @State private var isHovered = false

    func body(content: Content) -> some View {
        let activeTheme = appState.appTheme
        content
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected
                          ? appState.themeAccent.opacity(activeTheme == "light" ? 0.25 : 0.15)
                          : (isHovered ? (activeTheme == "light" ? Color.black.opacity(0.04) : Color.white.opacity(0.04)) : Color.clear))
                    .padding(.horizontal, 6)
            )
            .onHover { hovering in
                withAnimation(.easeOut(duration: 0.1)) {
                    isHovered = hovering
                }
            }
    }
}

extension View {
    func sidebarRowStyle(isSelected: Bool) -> some View {
        self.modifier(SidebarRowModifier(isSelected: isSelected))
    }
}

private let threadListOutputFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    return formatter
}()

private func formatThreadDate(_ iso: String) -> String {
    guard let date = parseMWDate(iso) else { return iso }
    return threadListOutputFormatter.string(from: date)
}

/// Root of a secondary (aux) window. Renders one surface, pinned to the target
/// passed via `openWindow(id:"aux", value:)`. Each detail view is `isEmbedded`
/// so it loads from the explicit id and never writes the main window's shared
/// nav/tab state. No sidebar — a focused single-surface window.
struct AuxWindowRootView: View {
    let target: AuxWindowTarget?
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if !appState.isAuthenticated {
                // macOS may restore an aux window on relaunch before sign-in;
                // don't render a detail view that would fire token-less requests.
                Text("Sign in to Werk to open this window.")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                switch target {
                case .project(let id):
                    ProjectDetailView(projectId: id, isEmbedded: true)
                case .channel(let id):
                    ChannelDetailView(channelId: id, isEmbedded: true)
                case .thread(let id):
                    ThreadDetailView(threadId: id, isEmbedded: true)
                case .journal(let id):
                    JournalDetailView(journalId: id, isEmbedded: true)
                case nil:
                    Text("Nothing to show")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .frame(minWidth: 480, minHeight: 400)
        .background(appState.themeBg)
    }
}

/// Full-pane home for archived material across all four surfaces. Reachable
/// from the sidebar footer "Archive" button. Each row opens the item (restoring
/// it to the detail pane) or restores it back to its active section.
struct ArchiveView: View {
    @Environment(AppState.self) private var appState
    @State private var projects: [MWProject] = []
    @State private var threads: [MWThread] = []
    @State private var journals: [MWJournal] = []
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true

    private var isEmpty: Bool {
        projects.isEmpty && threads.isEmpty && journals.isEmpty && channels.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 8) {
                    Image(systemName: "archivebox").foregroundColor(appState.themeAccent)
                    Text("Archive").font(.system(size: 16, weight: .semibold)).foregroundColor(appState.themeText)
                }
                if isLoading {
                    ProgressView().tint(.secondary).frame(maxWidth: .infinity).padding(.top, 40)
                } else if isEmpty {
                    Text("Nothing archived.")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                        .frame(maxWidth: .infinity).padding(.top, 40)
                } else {
                    if !projects.isEmpty {
                        section("Projects", "folder") {
                            ForEach(projects) { p in
                                row(p.title, "folder",
                                    open: { open { appState.selectedProjectId = p.id } },
                                    restore: { restoreProject(p) })
                            }
                        }
                    }
                    if !threads.isEmpty {
                        section("Threads", "bubble.left.and.bubble.right") {
                            ForEach(threads) { t in
                                row(t.title, "bubble.left.and.bubble.right",
                                    open: { open { appState.selectedThreadId = t.id } },
                                    restore: { restoreThread(t) })
                            }
                        }
                    }
                    if !journals.isEmpty {
                        section("Journals", "book.closed") {
                            ForEach(journals) { j in
                                row(j.title, "book.closed",
                                    open: { open { appState.selectedJournalId = j.id } },
                                    restore: { restoreJournal(j) })
                            }
                        }
                    }
                    if !channels.isEmpty {
                        section("Channels", "number") {
                            ForEach(channels) { c in
                                row(c.name, "number",
                                    open: { open { appState.selectedChannelId = c.id; appState.showChannelBrowse = false } },
                                    restore: { restoreChannel(c) })
                            }
                        }
                    }
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(appState.themeBg)
        .task { await load() }
    }

    @ViewBuilder
    private func section<Content: View>(_ title: String, _ icon: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
            content()
        }
    }

    private func row(_ title: String, _ icon: String, open: @escaping () -> Void, restore: @escaping () -> Void) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 12)).foregroundColor(appState.themeTextSecondary).frame(width: 16)
            Text(title.isEmpty ? "Untitled" : title)
                .font(.system(size: 13)).foregroundColor(appState.themeText).lineLimit(1)
            Spacer()
            Button("Restore", action: restore)
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeAccent)
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(appState.themeCard.opacity(0.5))
        .cornerRadius(6)
        .contentShape(Rectangle())
        .onTapGesture(perform: open)
    }

    private func open(_ select: () -> Void) {
        appState.selectedThreadId = nil; appState.selectedProjectId = nil
        appState.selectedChannelId = nil; appState.selectedJournalId = nil
        appState.selectedEmailId = nil
        appState.showInbox = false; appState.showPeople = false; appState.showSkills = false
        appState.showChannelBrowse = false; appState.showArchive = false
        select()
    }

    private func load() async {
        async let p = (try? await MatchaWorkService.shared.listProjects(status: "archived")) ?? []
        async let t = (try? await MatchaWorkService.shared.listThreads(status: "archived")) ?? []
        async let j = (try? await JournalService.shared.listArchivedJournals()) ?? []
        async let c = (try? await ChannelsService.shared.listArchivedChannels()) ?? []
        let (pp, tt, jj, cc) = await (p, t, j, c)
        await MainActor.run {
            projects = pp; threads = tt; journals = jj; channels = cc; isLoading = false
        }
    }

    private func restoreProject(_ p: MWProject) {
        Task {
            try? await MatchaWorkService.shared.unarchiveProject(id: p.id)
            MatchaWorkService.shared.invalidateProjectLists()
            await MainActor.run { projects.removeAll { $0.id == p.id }; appState.projectsListGeneration &+= 1 }
        }
    }
    private func restoreThread(_ t: MWThread) {
        Task {
            try? await MatchaWorkService.shared.unarchiveThread(id: t.id)
            MatchaWorkService.shared.invalidateThreadLists()
            await MainActor.run {
                threads.removeAll { $0.id == t.id }
                NotificationCenter.default.post(name: .mwThreadsChanged, object: nil)
            }
        }
    }
    private func restoreJournal(_ j: MWJournal) {
        Task {
            try? await JournalService.shared.unarchiveJournal(id: j.id)
            await MainActor.run { journals.removeAll { $0.id == j.id }; appState.journalsListGeneration &+= 1 }
        }
    }
    private func restoreChannel(_ c: ChannelSummary) {
        Task {
            try? await ChannelsService.shared.unarchiveChannel(id: c.id)
            await MainActor.run { channels.removeAll { $0.id == c.id }; appState.channelsListGeneration &+= 1 }
        }
    }
}


