import SwiftUI

struct ChannelsSidebarView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    var showHeader: Bool = true
    var searchText: String = ""
    /// When false, the section is collapsed in the sidebar: only **starred**
    /// channels render (a pinned strip), and the "Show N more" pager is hidden.
    /// Non-starred channels are revealed only when the user expands the header.
    var expanded: Bool = true
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var showDiscover = false
    @State private var errorMessage: String?
    @State private var channelPendingDelete: ChannelSummary?
    @State private var channelPendingLeave: ChannelSummary?
    @State private var isDeleting = false
    @State private var visibleCount = 3
    private let pageSize = 3
    @State private var isLeaving = false
    @AppStorage("channel-admin-wizard-shown-v1") private var hasSeenWizard = false

    var body: some View {
        content
            .background(Color.clear)
            .task { await load() }
            .onReceive(NotificationCenter.default.publisher(for: .mwChannelCreated)) { note in
                // Selection-only side effect. The reload is driven by the
                // `channelsListGeneration` bump that fires alongside this
                // notification — duplicating it here caused two concurrent
                // GET /channels calls on every channel create.
                if let newId = note.object as? String {
                    appState.selectedChannelId = newId
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedJournalId = nil
                }
            }
            .onChange(of: appState.channelsListGeneration) { _, _ in
                Task { await load() }
            }
            .sheet(isPresented: $showCreate) {
                CreateChannelSheet { newChannel in
                    appState.channelsListGeneration &+= 1
                    NotificationCenter.default.post(name: .mwChannelCreated, object: newChannel.id)
                }
            }
            .sheet(isPresented: $showDiscover) {
                DiscoverChannelsSheet { joinedId in
                    appState.channelsListGeneration &+= 1
                    appState.selectedChannelId = joinedId
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedJournalId = nil
                }
            }
            .confirmationDialog(
                channelPendingDelete.map { "Delete #\($0.name)?" } ?? "Delete channel?",
                isPresented: deleteDialogBinding,
                titleVisibility: .visible,
                presenting: channelPendingDelete
            ) { channel in
                Button("Delete", role: .destructive) {
                    Task { await delete(channel) }
                }
                Button("Cancel", role: .cancel) {}
            } message: { channel in
                Text(channel.isPaid
                    ? "This will archive the channel, cancel all active paid subscriptions, and notify members. This cannot be undone."
                    : "This will archive the channel and notify members. This cannot be undone.")
            }
            .confirmationDialog(
                channelPendingLeave.map { "Leave #\($0.name)?" } ?? "Leave channel?",
                isPresented: leaveDialogBinding,
                titleVisibility: .visible,
                presenting: channelPendingLeave
            ) { channel in
                Button("Leave", role: .destructive) {
                    Task { await leave(channel) }
                }
                Button("Cancel", role: .cancel) {}
            } message: { channel in
                Text(channel.isPaid
                    ? "You'll stop receiving messages in this channel and your paid subscription will be canceled at the period end."
                    : "You'll stop receiving messages in this channel. Rejoining later requires a re-invite if it's private.")
            }
    }

    private var leaveDialogBinding: Binding<Bool> {
        Binding(
            get: { channelPendingLeave != nil },
            set: { if !$0 { channelPendingLeave = nil } }
        )
    }

    @ViewBuilder
    private var content: some View {
        // Observe the star store so the pinned strip recomputes when a star is
        // toggled (membership of `displayChannels` depends on it).
        let _ = ChannelStarStore.shared.generation
        VStack(spacing: 0) {
            if showHeader {
                header
                Divider().opacity(0.3)
            }
            if isLoading {
                // No "Loading…" placeholder in a collapsed pinned strip.
                if expanded { loadingView }
            } else if displayChannels.isEmpty {
                // Collapsed + nothing starred → render nothing (stays collapsed).
                if expanded { emptyView }
            } else {
                channelList
            }
        }
    }

    /// Channels shown right now: everything when expanded, only starred when the
    /// section is collapsed (the pinned strip).
    private var displayChannels: [ChannelSummary] {
        guard !expanded else { return channels }
        let stars = ChannelStarStore.shared
        return channels.filter { stars.isStarred($0.id) }
    }

    private var loadingView: some View {
        Text("Loading…")
            .font(.system(size: 11))
            .foregroundColor(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, 16)
    }

    private var emptyView: some View {
        VStack(spacing: 8) {
            Text("No channels yet")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            Button {
                showCreate = true
            } label: {
                Text("Create one")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeAccent)
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.vertical, 16)
    }

    private var channelList: some View {
        let filtered = displayChannels.filter {
            searchText.isEmpty || $0.name.localizedCaseInsensitiveContains(searchText)
        }
        // Collapsed strip shows every starred channel (few); pager only paginates
        // the full expanded list.
        let paginate = expanded && searchText.isEmpty
        let limit = paginate ? visibleCount : filtered.count
        return LazyVStack(spacing: 0) {
            ForEach(filtered.prefix(limit), id: \.id) { channel in
                row(for: channel)
            }
            if paginate && filtered.count > visibleCount {
                SidebarShowMoreButton(remaining: filtered.count - visibleCount, pageSize: pageSize) {
                    visibleCount += pageSize
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var deleteDialogBinding: Binding<Bool> {
        Binding(
            get: { channelPendingDelete != nil },
            set: { if !$0 { channelPendingDelete = nil } }
        )
    }

    private var header: some View {
        HStack(spacing: 6) {
            Text("Channels")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Button {
                showDiscover = true
            } label: {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .help("Discover public channels")
            Button {
                showCreate = true
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .help("Create a channel")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private func row(for channel: ChannelSummary) -> some View {
        let selected = appState.selectedChannelId == channel.id
        let unread = channel.unreadCount + (appState.channelUnreadOverrides[channel.id] ?? 0)
        // Observe ChannelStarStore.generation so the row redraws when the
        // user toggles a star elsewhere (context menu, etc).
        _ = ChannelStarStore.shared.generation
        let isStarred = ChannelStarStore.shared.isStarred(channel.id)
        return Button {
            appState.selectedChannelId = channel.id
            appState.showChannelBrowse = false
            appState.clearChannelUnread(channel.id)
            // Zero the API-sourced count locally so the badge stays cleared
            // after the user clicks elsewhere. Backend marks last_read_at on
            // getChannel; next listChannels() refetch returns 0 too.
            if let idx = channels.firstIndex(where: { $0.id == channel.id }) {
                channels[idx].unreadCount = 0
            }
            appState.selectedThreadId = nil
            appState.selectedProjectId = nil
            appState.selectedJournalId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            HStack(alignment: .center, spacing: 8) {
                Image(systemName: isStarred ? "star.fill" : "number")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(isStarred ? .yellow : (selected ? appState.themeAccent : appState.themeTextSecondary))
                    .frame(width: 14)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(channel.name)
                            .font(.system(size: 13, weight: selected ? .bold : (unread > 0 ? .semibold : .regular)))
                            .foregroundColor(selected ? appState.themeText : appState.themeText.opacity(0.9))
                            .lineLimit(1)
                        if channel.projectId != nil {
                            Text("collab")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(appState.themeAccent)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(
                                    RoundedRectangle(cornerRadius: 3)
                                        .fill(appState.themeAccent.opacity(0.15))
                                )
                        }
                        Spacer(minLength: 4)
                        if unread > 0 {
                            Text(unread > 99 ? "99+" : "\(unread)")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(Capsule().fill(appState.themeAccent))
                        }
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .sidebarRowStyle(isSelected: selected)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button {
                openWindow(id: "aux", value: AuxWindowTarget.channel(channel.id))
            } label: {
                Label("Open in new window", systemImage: "macwindow.on.rectangle")
            }
            Button {
                appState.splitTarget = .channel(channel.id)
            } label: {
                Label("Open in split", systemImage: "rectangle.split.2x1")
            }
            Button {
                appState.bottomSplitTarget = .channel(channel.id)
            } label: {
                Label("Open in bottom split", systemImage: "rectangle.split.1x2")
            }
            Divider()
            // Jump to the linked collab project even when it isn't starred —
            // the project loads via getProjectDetail regardless of pinning.
            // Mirrors the project-open in ContentView.starredProjectRow.
            if let pid = channel.projectId {
                Button {
                    appState.selectedProjectId = pid
                    appState.selectedThreadId = nil
                    appState.selectedJournalId = nil
                    appState.selectedChannelId = nil
                    appState.showInbox = false
                    appState.showSkills = false
                } label: {
                    Label("Open collab project", systemImage: "folder")
                }
                Divider()
            }
            // Star toggle — drives macOS push notifications + sort. Per-user
            // local state so it can't be shared across devices in v1.
            Button {
                ChannelStarStore.shared.toggle(channel.id)
                Task { await load() }   // re-sort starred-first immediately
            } label: {
                Label(
                    isStarred ? "Unstar channel" : "Star channel",
                    systemImage: isStarred ? "star.slash" : "star",
                )
            }
            let role = channel.myRole ?? ""
            let isAdmin = (appState.currentUser?.role ?? "") == "admin"
            // Members (and owners after they transfer) can leave. Owners
            // see Delete instead — leaving while owning the channel is
            // rejected server-side anyway.
            if !role.isEmpty && role != "owner" {
                Divider()
                Button(role: .destructive) {
                    channelPendingLeave = channel
                } label: {
                    Label("Leave channel", systemImage: "arrow.right.square")
                }
            }
            if role == "owner" || isAdmin {
                Divider()
                Button(role: .destructive) {
                    channelPendingDelete = channel
                } label: {
                    Label("Delete channel", systemImage: "trash")
                }
            }
        }
    }

    private func leave(_ channel: ChannelSummary) async {
        isLeaving = true
        defer { isLeaving = false }
        do {
            try await ChannelsService.shared.leaveChannel(id: channel.id)
            if appState.selectedChannelId == channel.id {
                appState.selectedChannelId = nil
            }
            appState.channelsListGeneration &+= 1
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func delete(_ channel: ChannelSummary) async {
        isDeleting = true
        defer { isDeleting = false }
        do {
            try await ChannelsService.shared.deleteChannel(id: channel.id)
            if appState.selectedChannelId == channel.id {
                appState.selectedChannelId = nil
            }
            // Bumping the generation counter triggers `.onChange` -> load().
            // Don't call load() inline here too; it would fire a duplicate GET.
            appState.channelsListGeneration &+= 1
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func isRecentlyActive(_ dateString: String?, days: Int = 7) -> Bool {
        guard let ds = dateString, let date = parseMWDate(ds) else { return true }
        return Date().timeIntervalSince(date) < Double(days) * 86_400
    }

    private func load() async {
        do {
            let list = try await ChannelsService.shared.listChannels()
            // Starred channels float to the top, then by last activity.
            // Star state is per-user UserDefaults — bound at login by AppState.
            // Channels with no activity in 7+ days are hidden (starred bypass this).
            let stars = ChannelStarStore.shared
            channels = list
                .filter { ch in stars.isStarred(ch.id) || isRecentlyActive(ch.lastMessageAt) }
                .sorted { a, b in
                    let sa = stars.isStarred(a.id)
                    let sb = stars.isStarred(b.id)
                    if sa != sb { return sa && !sb }
                    return (a.lastMessageAt ?? "") > (b.lastMessageAt ?? "")
                }
            // Subscribe to all member channels so background messages arrive.
            ChannelsWebSocket.shared.joinBackgroundRooms(list.map { (id: $0.id, name: $0.name) })
            // API returned fresh unread counts — local overrides are now stale.
            appState.channelUnreadOverrides = [:]
            // Mirror server unread into AppState so channel *tabs* can badge
            // without the sidebar's local list in scope.
            appState.channelUnreadCounts = Dictionary(
                list.map { ($0.id, $0.unreadCount) }, uniquingKeysWith: { a, _ in a }
            )
            isLoading = false
            maybeAutoShowAdminWizard(list)
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    /// Show the channel admin wizard once on first launch for likely admins:
    /// personal/individual users (creator track) OR users who already own a
    /// channel. Single-shot — `hasSeenWizard` flips true after the user
    /// closes the wizard.
    private func maybeAutoShowAdminWizard(_ list: [ChannelSummary]) {
        guard !hasSeenWizard else { return }
        guard !appState.showChannelAdminWizard else { return }
        let role = appState.currentUser?.role ?? ""
        let isCreatorTrack = role == "individual" || role == "admin"
        let ownsChannel = list.contains { ($0.myRole ?? "") == "owner" }
        guard isCreatorTrack || ownsChannel else { return }
        appState.channelAdminWizardMode = .create
        appState.showChannelAdminWizard = true
    }
}

extension Notification.Name {
    static let mwChannelCreated = Notification.Name("mwChannelCreated")
}

struct CreateChannelSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState
    let onCreated: (ChannelDetail) -> Void

    @State private var name = ""
    @State private var description = ""
    @State private var visibility = "public"
    @State private var category: ChannelCategory = .general
    @State private var isPaid = false
    @State private var priceDollars = "5"
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @FocusState private var nameFocused: Bool

    // Paid/creator channels are for personal accounts only. Matches the
    // backend rule in /channels POST (role must be individual or admin)
    // and the web client's canCreatePaid gating.
    private var canCreatePaid: Bool {
        let role = appState.currentUser?.role ?? ""
        return role == "individual" || role == "admin"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("create channel")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            VStack(alignment: .leading, spacing: 4) {
                Text("name")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                HStack(spacing: 6) {
                    TextField("", text: $name, prompt: Text("general").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.9))
                        .focused($nameFocused)
                    EmojiPaletteButton { nameFocused = true }
                }
                Divider()
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("description")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                TextField("", text: $description, prompt: Text("optional").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(1...3)
                Divider()
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("category")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                Picker("", selection: $category) {
                    ForEach(ChannelCategory.allCases) { cat in
                        Text(cat.label).tag(cat)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
                Divider()
            }

            HStack(spacing: 16) {
                visibilityButton(label: "public")
                visibilityButton(label: "private")
                Spacer()
            }

            if canCreatePaid, !appState.canPaidChannels {
                // Role-eligible but plan-locked: creator monetization is Pro.
                Button {
                    appState.presentPaywall(for: "paid_channels")
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "lock.fill")
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.45))
                        Text("paid (subscribers only)")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.5))
                        Spacer()
                        Text("PRO")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(appState.themeAccent)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(appState.themeAccent.opacity(0.15))
                            .cornerRadius(4)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else if canCreatePaid {
                Toggle(isOn: $isPaid) {
                    Text("paid (subscribers only)")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.7))
                }
                .toggleStyle(.switch)
                .controlSize(.small)

                if isPaid {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("price / month (usd)")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.4))
                        HStack(spacing: 4) {
                            Text("$")
                                .font(.system(size: 13))
                                .foregroundColor(.white.opacity(0.5))
                            TextField("", text: $priceDollars, prompt: Text("5").foregroundColor(.white.opacity(0.25)))
                                .textFieldStyle(.plain)
                                .font(.system(size: 13))
                                .foregroundColor(.white.opacity(0.9))
                        }
                        Divider()
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red.opacity(0.8))
            }

            HStack {
                Button {
                    dismiss()
                } label: {
                    Text("cancel")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    Task { await create() }
                } label: {
                    if isSubmitting {
                        Text("creating…")
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.4))
                    } else {
                        Text("create")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(
                                name.trimmingCharacters(in: .whitespaces).isEmpty
                                    ? .white.opacity(0.25)
                                    : Color.matcha500
                            )
                    }
                }
                .buttonStyle(.plain)
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || isSubmitting)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 360)
        .background(Color.appBackground)
    }

    private func visibilityButton(label: String) -> some View {
        let active = visibility == label
        return Button {
            visibility = label
        } label: {
            VStack(spacing: 2) {
                Text(label)
                    .font(.system(size: 11))
                    .foregroundColor(active ? Color.matcha500 : .white.opacity(0.5))
                Rectangle()
                    .fill(active ? Color.matcha500 : Color.clear)
                    .frame(height: 1)
            }
        }
        .buttonStyle(.plain)
    }

    private func create() async {
        isSubmitting = true
        errorMessage = nil
        var paidConfig: ChannelsService.PaidChannelConfig? = nil
        if isPaid && canCreatePaid {
            guard let dollars = Double(priceDollars.trimmingCharacters(in: .whitespaces)), dollars > 0 else {
                errorMessage = "Enter a valid price"
                isSubmitting = false
                return
            }
            let cents = Int((dollars * 100).rounded())
            paidConfig = ChannelsService.PaidChannelConfig(
                priceCents: cents,
                currency: "usd",
                inactivityThresholdDays: nil,
                inactivityWarningDays: 3
            )
        }
        do {
            let channel = try await ChannelsService.shared.createChannel(
                name: name.trimmingCharacters(in: .whitespaces),
                description: description.isEmpty ? nil : description,
                visibility: visibility,
                category: category.rawValue,
                paidConfig: paidConfig
            )
            onCreated(channel)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            isSubmitting = false
        }
    }
}

// MARK: - Channels hub (full-pane dashboard)

/// Full-pane "Channels" hub — opened from the sidebar Channels nav row. Lists
/// the channels you're in; filter (Starred / Mine), create, and browse-public
/// live here. Picking a card sets `selectedChannelId` so the channel opens over
/// the hub.
struct ChannelsLibraryView: View {
    @Environment(AppState.self) private var appState

    @State private var channels: [ChannelSummary] = []
    /// Public channels the user could join (GET /channels/discover —
    /// already excludes memberships). Third hub section.
    @State private var discover: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var search = ""
    @State private var showCreate = false
    @State private var starGen = 0
    @State private var railSearch = ""
    @State private var railCollapsed = false
    /// Channel id with a join request in flight (spinner on that card).
    @State private var joiningId: String?

    private let columns = [GridItem(.adaptive(minimum: 220, maximum: 300), spacing: 14)]

    var body: some View {
        HSplitView {
            if railCollapsed {
                MWHubRailStrip { railCollapsed = false }
            } else {
                rail.frame(minWidth: 232, idealWidth: 258, maxWidth: 320)
            }
            Group {
                if let id = appState.selectedChannelId {
                    ChannelDetailView(channelId: id)
                } else {
                    VStack(spacing: 0) {
                        header
                        Divider().background(appState.themeBorder)
                        content
                    }
                    .background(ThemeRadialBackground())
                }
            }
            .frame(minWidth: 420, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await load() }
        .onChange(of: appState.channelsListGeneration) { _, _ in Task { await load() } }
        .sheet(isPresented: $showCreate) {
            CreateChannelSheet { ch in
                appState.channelsListGeneration &+= 1
                open(ch.id)
            }
        }
    }

    // ── Rail ────────────────────────────────────────────────────────────
    private var railChannels: [ChannelSummary] {
        _ = starGen
        let stars = ChannelStarStore.shared
        var out = channels.filter { $0.isMember }
        if !railSearch.isEmpty { out = out.filter { $0.name.localizedCaseInsensitiveContains(railSearch) } }
        return out.sorted { (stars.isStarred($0.id) ? 1 : 0, $0.lastMessageAt ?? "") > (stars.isStarred($1.id) ? 1 : 0, $1.lastMessageAt ?? "") }
    }

    private var rail: some View {
        MWHubRail {
            VStack(spacing: 8) {
                HStack {
                    Text("Channels").font(.system(size: 12, weight: .semibold)).foregroundColor(appState.themeTextSecondary)
                    Spacer()
                    MWHubRailIconButton(icon: "sidebar.left", help: "Hide sidebar") { railCollapsed = true }
                    MWHubRailIconButton(icon: "magnifyingglass", help: "Browse") { browse() }
                    MWHubRailIconButton(icon: "plus", help: "New channel") { showCreate = true }
                }
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    TextField("Filter", text: $railSearch).textFieldStyle(.plain)
                        .font(.system(size: 11)).foregroundColor(appState.themeText)
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(Capsule().fill(appState.themeText.opacity(0.06)))
            }
        } rows: {
            MWHubRailRow(icon: "square.grid.2x2", title: "All Channels",
                         selected: appState.selectedChannelId == nil) {
                appState.selectedChannelId = nil
            }
            ForEach(railChannels) { c in
                let starred = ChannelStarStore.shared.isStarred(c.id)
                // Crown marks channels you run, so yours read at a glance.
                MWHubRailRow(icon: starred ? "star.fill" : (c.myRole == "owner" ? "crown" : "number"),
                             title: c.name,
                             selected: appState.selectedChannelId == c.id,
                             accent: starred,
                             trailing: c.unreadCount > 0 ? "\(min(c.unreadCount, 99))" : nil) { open(c.id) }
                    .contextMenu {
                        Button(starred ? "Unstar" : "Star") { ChannelStarStore.shared.toggle(c.id); starGen += 1 }
                        Divider()
                        AuxOpenMenuButtons(target: .channel(c.id))
                    }
            }
        }
    }

    // ── Sections — the three kinds of channels ──────────────────────────
    // "Yours" = channels you own; "Joined" = member but someone else runs it;
    // "Open to join" = public channels from /discover you're not in yet.

    private func searched(_ list: [ChannelSummary]) -> [ChannelSummary] {
        guard !search.isEmpty else { return list }
        return list.filter {
            $0.name.localizedCaseInsensitiveContains(search)
                || ($0.description?.localizedCaseInsensitiveContains(search) ?? false)
        }
    }

    private func sortedByStar(_ list: [ChannelSummary]) -> [ChannelSummary] {
        _ = starGen
        let stars = ChannelStarStore.shared
        return list.sorted { (stars.isStarred($0.id) ? 1 : 0, $0.lastMessageAt ?? "") > (stars.isStarred($1.id) ? 1 : 0, $1.lastMessageAt ?? "") }
    }

    private var mineChannels: [ChannelSummary] {
        sortedByStar(searched(channels.filter { $0.isMember && $0.myRole == "owner" }))
    }

    private var joinedChannels: [ChannelSummary] {
        sortedByStar(searched(channels.filter { $0.isMember && $0.myRole != "owner" }))
    }

    private var joinableChannels: [ChannelSummary] {
        searched(discover)
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Channels").font(.system(size: 20, weight: .bold)).foregroundColor(appState.themeText)
                    Text("Team spaces and real-time conversations")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                Button { browse() } label: {
                    HStack(spacing: 5) { Image(systemName: "magnifyingglass"); Text("Browse").font(.system(size: 12, weight: .semibold)) }
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(appState.themeAccent.opacity(0.10)).foregroundColor(appState.themeAccent).cornerRadius(8)
                }
                .buttonStyle(.plain)
                Button { showCreate = true } label: {
                    HStack(spacing: 5) { Image(systemName: "plus"); Text("New Channel").font(.system(size: 12, weight: .semibold)) }
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
            HStack(spacing: 8) {
                Spacer()
                MWHubSearch(text: $search)
            }
        }
        .padding(20)
    }

    @ViewBuilder private var content: some View {
        if isLoading {
            Spacer(); ProgressView().tint(appState.themeTextSecondary); Spacer()
        } else if mineChannels.isEmpty && joinedChannels.isEmpty && joinableChannels.isEmpty {
            MWHubEmpty(icon: "number",
                       title: search.isEmpty ? "No channels yet" : "No channels match",
                       cta: "New Channel") { showCreate = true }
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    section(title: "Started by you", icon: "crown.fill",
                            subtitle: "Channels you run", items: mineChannels, joinable: false)
                    section(title: "Joined", icon: "person.2.fill",
                            subtitle: "Channels run by others", items: joinedChannels, joinable: false)
                    section(title: "Open to join", icon: "sparkles",
                            subtitle: "Public channels from the community", items: joinableChannels, joinable: true)
                }
                .padding(20)
            }
        }
    }

    @ViewBuilder
    private func section(title: String, icon: String, subtitle: String,
                         items: [ChannelSummary], joinable: Bool) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 7) {
                    Image(systemName: icon)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                    Text("\(items.count)")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 1)
                        .background(Capsule().fill(appState.themeText.opacity(0.07)))
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                    Spacer()
                }
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(items) { c in card(c, joinable: joinable) }
                }
            }
        }
    }

    private func card(_ c: ChannelSummary, joinable: Bool) -> some View {
        let starred = ChannelStarStore.shared.isStarred(c.id)
        let isMine = c.myRole == "owner"
        return Button {
            if joinable { join(c) } else { open(c.id) }
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                // Founder row — who runs this channel.
                HStack(spacing: 7) {
                    ChannelAvatarView(senderId: c.createdById ?? c.id,
                                      payloadURL: c.createdByAvatarUrl,
                                      name: c.createdByName ?? c.name,
                                      size: 22)
                    Text(isMine ? "Run by you" : "by \(c.createdByName ?? "Unknown")")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(isMine ? appState.themeAccent : appState.themeTextSecondary)
                        .lineLimit(1)
                    Spacer()
                    if c.isPaid {
                        Image(systemName: "dollarsign.circle.fill").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    }
                    if c.visibility == "private" {
                        Image(systemName: "lock.fill").font(.system(size: 9)).foregroundColor(appState.themeTextSecondary)
                    }
                    if c.unreadCount > 0 {
                        Text("\(min(c.unreadCount, 99))")
                            .font(.system(size: 8, weight: .bold)).foregroundColor(appState.themeOnAccent)
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Capsule().fill(appState.themeAccent))
                    }
                }
                HStack(spacing: 5) {
                    Image(systemName: starred ? "star.fill" : "number")
                        .font(.system(size: 12)).foregroundColor(starred ? appState.themeAccent : appState.themeTextSecondary)
                    Text(c.name).font(.system(size: 13, weight: .semibold)).foregroundColor(appState.themeText).lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let d = c.description, !d.isEmpty {
                    Text(d).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary).lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Spacer(minLength: 0)
                // Footer: members · topic · join affordance.
                HStack(spacing: 8) {
                    HStack(spacing: 3) {
                        Image(systemName: "person.2").font(.system(size: 9))
                        Text("\(c.memberCount)").font(.system(size: 10, weight: .medium))
                    }
                    .foregroundColor(appState.themeTextSecondary)
                    if let cat = c.category, !cat.isEmpty {
                        Text(cat.capitalized)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundColor(appState.themeTextSecondary)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Capsule().fill(appState.themeText.opacity(0.06)))
                    }
                    Spacer()
                    if joinable {
                        if joiningId == c.id {
                            ProgressView().controlSize(.mini)
                        } else {
                            Text(c.isPaid ? "View" : "Join")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(appState.themeOnAccent)
                                .padding(.horizontal, 10).padding(.vertical, 3)
                                .background(Capsule().fill(appState.themeAccent))
                        }
                    }
                }
            }
            .padding(14).frame(height: 132, alignment: .top)
            .background(RoundedRectangle(cornerRadius: 10).fill(appState.themeCard))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isMine ? appState.themeAccent.opacity(0.35) : appState.themeBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            if !joinable {
                Button(starred ? "Unstar" : "Star") {
                    ChannelStarStore.shared.toggle(c.id); starGen += 1
                }
            }
        }
    }

    /// Free public channel → join inline and open it. Paid → route to the
    /// Browse surface, which owns the subscribe flow.
    private func join(_ c: ChannelSummary) {
        if c.isPaid { browse(); return }
        guard joiningId == nil else { return }
        joiningId = c.id
        Task {
            defer { joiningId = nil }
            do {
                try await ChannelsService.shared.joinChannel(id: c.id)
                await load()
                open(c.id)
            } catch {
                print("[ChannelsHub] join failed: \(error)")
            }
        }
    }

    private func open(_ id: String) {
        appState.selectedChannelId = id   // hub flag stays set → back returns here
        appState.selectedThreadId = nil; appState.selectedProjectId = nil
        appState.selectedJournalId = nil; appState.selectedEmailId = nil
    }

    private func browse() {
        appState.showChannelBrowse = true
        appState.showChannelsHub = false
        appState.selectedThreadId = nil; appState.selectedProjectId = nil
        appState.selectedChannelId = nil; appState.selectedJournalId = nil
    }

    private func load() async {
        async let mineTask = ChannelsService.shared.listChannels()
        async let discoverTask = ChannelsService.shared.discoverChannels()
        let list = (try? await mineTask) ?? []
        let open = (try? await discoverTask) ?? []
        await MainActor.run { channels = list; discover = open; isLoading = false }
    }
}
