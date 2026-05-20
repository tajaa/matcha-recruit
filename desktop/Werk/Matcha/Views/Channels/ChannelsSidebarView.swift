import SwiftUI

struct ChannelsSidebarView: View {
    @Environment(AppState.self) private var appState
    var showHeader: Bool = true
    var searchText: String = ""
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var showDiscover = false
    @State private var errorMessage: String?
    @State private var channelPendingDelete: ChannelSummary?
    @State private var channelPendingLeave: ChannelSummary?
    @State private var isDeleting = false
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
        VStack(spacing: 0) {
            if showHeader {
                header
                Divider().opacity(0.3)
            }
            if isLoading {
                loadingView
            } else if channels.isEmpty {
                emptyView
            } else {
                channelList
            }
        }
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
        let filtered = channels.filter {
            searchText.isEmpty || $0.name.localizedCaseInsensitiveContains(searchText)
        }
        return LazyVStack(spacing: 0) {
            ForEach(filtered, id: \.id) { channel in
                row(for: channel)
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
                            .font(.system(size: 13, weight: (selected || unread > 0) ? .semibold : .regular))
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
                    if let preview = channel.lastMessagePreview, !preview.isEmpty {
                        Text(preview)
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeTextSecondary)
                            .lineLimit(1)
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

    private func load() async {
        do {
            let list = try await ChannelsService.shared.listChannels()
            // Starred channels float to the top, then by last activity.
            // Star state is per-user UserDefaults — bound at login by AppState.
            let stars = ChannelStarStore.shared
            channels = list.sorted { a, b in
                let sa = stars.isStarred(a.id)
                let sb = stars.isStarred(b.id)
                if sa != sb { return sa && !sb }
                return (a.lastMessageAt ?? "") > (b.lastMessageAt ?? "")
            }
            // Subscribe to all member channels so background messages arrive.
            ChannelsWebSocket.shared.joinBackgroundRooms(list.map { (id: $0.id, name: $0.name) })
            // API returned fresh unread counts — local overrides are now stale.
            appState.channelUnreadOverrides = [:]
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
                TextField("", text: $name, prompt: Text("general").foregroundColor(.white.opacity(0.25)))
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.9))
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

            if canCreatePaid {
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
