import SwiftUI

struct ChannelsSidebarView: View {
    @Environment(AppState.self) private var appState
    var showHeader: Bool = true
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var errorMessage: String?
    @State private var channelPendingDelete: ChannelSummary?
    @State private var isDeleting = false

    var body: some View {
        content
            .background(Color.appBackground)
            .task { await load() }
            .onReceive(NotificationCenter.default.publisher(for: .mwChannelCreated)) { note in
                // Selection-only side effect. The reload is driven by the
                // `channelsListGeneration` bump that fires alongside this
                // notification — duplicating it here caused two concurrent
                // GET /channels calls on every channel create.
                if let newId = note.object as? String {
                    appState.selectedChannelId = newId
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
        VStack {
            Spacer()
            Text("Loading…")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            Spacer()
        }
    }

    private var emptyView: some View {
        VStack {
            Spacer()
            VStack(spacing: 8) {
                Text("No channels yet")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Button {
                    showCreate = true
                } label: {
                    Text("Create one")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color.matcha500)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
    }

    private var channelList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(channels, id: \.id) { channel in
                    row(for: channel)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var deleteDialogBinding: Binding<Bool> {
        Binding(
            get: { channelPendingDelete != nil },
            set: { if !$0 { channelPendingDelete = nil } }
        )
    }

    private var header: some View {
        HStack {
            Text("Channels")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
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
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private func row(for channel: ChannelSummary) -> some View {
        let selected = appState.selectedChannelId == channel.id
        let unread = channel.unreadCount + (appState.channelUnreadOverrides[channel.id] ?? 0)
        return Button {
            appState.selectedChannelId = channel.id
            appState.clearChannelUnread(channel.id)
            appState.selectedThreadId = nil
            appState.selectedProjectId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            HStack(alignment: .center, spacing: 8) {
                Image(systemName: "number")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(selected ? Color.matcha500 : .secondary)
                    .frame(width: 14)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(channel.name)
                            .font(.system(size: 13, weight: (selected || unread > 0) ? .semibold : .regular))
                            .foregroundColor(selected ? .primary : .primary.opacity(0.9))
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        if unread > 0 {
                            Text(unread > 99 ? "99+" : "\(unread)")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(Capsule().fill(Color.matcha500))
                        }
                    }
                    if let preview = channel.lastMessagePreview, !preview.isEmpty {
                        Text(preview)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(selected ? Color.matcha500.opacity(0.15) : Color.clear)
                    .padding(.horizontal, 6)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            let role = channel.myRole ?? ""
            let isAdmin = (appState.currentUser?.role ?? "") == "admin"
            if role == "owner" || isAdmin {
                Button(role: .destructive) {
                    channelPendingDelete = channel
                } label: {
                    Label("Delete channel", systemImage: "trash")
                }
            }
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
            channels = list.sorted {
                ($0.lastMessageAt ?? "") > ($1.lastMessageAt ?? "")
            }
            // API returned fresh unread counts — local overrides are now stale.
            appState.channelUnreadOverrides = [:]
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
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
