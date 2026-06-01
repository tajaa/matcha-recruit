import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ChannelDetailView: View {
    let channelId: String
    /// True when shown inside a collab project's chat panel. Embedded
    /// channels must NOT claim the workspace-tab active context — the
    /// enclosing project owns it (otherwise the collab project can't be pinned).
    var isEmbedded: Bool = false

    @Environment(AppState.self) private var appState
    @State private var vm = ChannelChatViewModel()
    @State private var inputText = ""

    @MainActor
    init(channelId: String, isEmbedded: Bool = false) {
        self.channelId = channelId
        self.isEmbedded = isEmbedded
        // Main-window tabs share a cached VM for instant warm re-entry; embedded
        // channels (collab project chat panel) keep a private VM so they never
        // share WS callbacks with a main tab on the same channel.
        _vm = State(initialValue: isEmbedded
            ? ChannelChatViewModel()
            : WorkDetailVMStore.shared.channelVM(channelId))
    }
    @State private var pendingAttachments: [PendingChannelAttachment] = []
    @State private var isUploading = false
    @State private var isDragOver = false
    @State private var replyingTo: ChannelMessage? = nil
    @State private var hoveredMessageId: String? = nil
    @State private var lastTypingSentAt: Date = .distantPast
    @State private var showInviteSheet = false
    @State private var showManageMembers = false
    @State private var pendingMessageDelete: ChannelMessage? = nil
    /// When set, the composer is editing this message instead of sending new.
    @State private var editingMessage: ChannelMessage? = nil
    @State private var inviteToast: String?
    /// Single hoisted attachment-preview target. Lives here (not per-row) so a
    /// streaming message / hover re-render or LazyVStack recycle can't drop the
    /// binding mid-present — that was the flaky-open bug.
    @State private var previewFile: MWProjectFile?
    // "Create ticket" from a message → AI draft → review sheet (project chats only).
    @State private var ticketDraft: MWTaskDraft?
    @State private var showTicketReview = false
    @State private var draftingTicket = false
    @State private var ticketDraftError: String?
    /// True while the bottom sentinel is on screen — gates message auto-scroll.
    @State private var isAtBottom = true
    /// Bumped whenever WE send a message, to force the viewport to the newest
    /// message regardless of scroll position — sending a reply should always
    /// reveal your own message without a manual scroll.
    @State private var selfSendScroll = 0
    // Chat → ticket always drafts with Flash Lite (cheap/fast for this
    // lightweight action), regardless of the header model selector.
    private var ticketDraftModel: String? {
        mwModelOptions.first { $0.id == "flash-lite" }?.value
    }

    @Environment(BroadcastService.self) private var broadcast: BroadcastService

    private var isAdmin: Bool {
        let role = vm.channel?.myRole ?? ""
        let global = appState.currentUser?.role ?? ""
        return role == "owner" || role == "moderator" || global == "admin"
    }

    private let ws = ChannelsWebSocket.shared
    private let senderColumnWidth: CGFloat = 160
    private let maxAttachments = 10
    private let maxAttachmentBytes = 50 * 1024 * 1024
    /// Permissive: block only executable / installer types; everything else
    /// (docs, markdown, code, images, video, audio, archives, …) is allowed.
    private let blockedExtensions: Set<String> = [
        "exe", "msi", "bat", "cmd", "com", "scr", "vbs", "ps1",
        "app", "dmg", "pkg", "deb", "rpm", "apk", "jar", "bin",
        "command", "scpt", "action", "workflow",
    ]

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if vm.isLoading && vm.channel == nil {
                // Cold load only — warm re-entry keeps the prior messages
                // visible and revalidates silently (no skeleton flash).
                ChatSkeleton()
            } else if let errorMessage = vm.errorMessage {
                Spacer()
                VStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 22))
                        .foregroundColor(.red)
                    Text(errorMessage)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeText.opacity(0.4))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 16)
                    Button {
                        Task {
                            vm.errorMessage = nil
                            await vm.loadChannel(channelId: channelId)
                        }
                    } label: {
                        Text("Try again").font(.system(size: 11, weight: .medium))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                    .controlSize(.small)
                }
                Spacer()
            } else {
                if broadcast.channelId == channelId && broadcast.isConnected {
                    BroadcastPanelView(
                        channelId: channelId,
                        channelName: vm.channel?.name ?? "channel",
                        isOwner: broadcast.isOwner,
                        members: vm.channel?.members ?? [],
                        myUserId: appState.currentUser?.id ?? "",
                    )
                        .environment(broadcast)
                    Divider()
                } else if let info = broadcast.activeBroadcasts[channelId],
                          info.startedBy != appState.currentUser?.id {
                    watchFeedBanner
                    Divider()
                }
                messagesList
                Divider()
                ChannelMessageComposer(
                    channelId: channelId,
                    channelSlug: channelSlug,
                    userHandle: userHandle,
                    members: vm.channel?.members ?? [],
                    currentUserId: appState.currentUser?.id ?? "",
                    maxAttachments: maxAttachments,
                    typingPing: { ws.sendTyping(channelId: channelId) },
                    onSend: send,
                    onOpenFilePicker: openFilePicker,
                    onPasteImage: pasteImageFromClipboard,
                    inputText: $inputText,
                    pendingAttachments: $pendingAttachments,
                    replyingTo: $replyingTo,
                    editingMessage: $editingMessage,
                    isUploading: $isUploading,
                    lastTypingSentAt: $lastTypingSentAt
                )
                .onDrop(of: [UTType.fileURL], isTargeted: $isDragOver) { providers in
                    handleFileDrop(providers)
                    return true
                }
            }
        }
        .background(appState.themeBg)
        .task(id: channelId) {
            // Re-point at this channel's cached VM (view is reused across
            // channel→channel switches). `resume` silently revalidates when the
            // VM is already warm for this channel, else falls back to a cold start.
            if !isEmbedded {
                let cached = WorkDetailVMStore.shared.channelVM(channelId)
                if cached !== vm { vm = cached }
            }
            await vm.resume(channelId: channelId)
            // REST fallback so a viewer who navigates into the channel mid-stream
            // (or whose WS dropped before the broadcast.started fan-out) still
            // sees the Watch-feed banner without depending on the WS event.
            await broadcast.fetchBroadcastStatus(channelId: channelId)
            if !isEmbedded {
                appState.setActiveContext(WorkTab(kind: .channel, entityId: channelId,
                                                  title: vm.channel?.name ?? "Channel"))
            }
        }
        .onChange(of: appState.foregroundTick) {
            // App regained focus — silently refetch in case the WS missed
            // messages while away (join_room doesn't backfill). isRefresh = no
            // loading flash, no list rebuild unless messages actually changed.
            Task { await vm.loadChannel(channelId: channelId, isRefresh: true) }
        }
        .onDisappear {
            // Don't leaveRoom — keep this channel subscribed via
            // joinBackgroundRooms so background message notifications still
            // arrive when the user is viewing a different channel/project.
            // The matching design intent is documented on joinRoom().
            vm.stop(channelId: channelId)
        }
        .sheet(isPresented: $showInviteSheet) {
            InviteToChannelSheet(
                channelId: channelId,
                channelName: vm.channel?.name ?? "channel"
            ) { addedCount in
                inviteToast = "Invited \(addedCount) member\(addedCount == 1 ? "" : "s")"
                Task { await vm.loadChannel(channelId: channelId) }
            }
        }
        .sheet(isPresented: $showManageMembers) {
            if let channel = vm.channel {
                ManageMembersSheet(
                    channelId: channelId,
                    channelName: channel.name,
                    members: channel.members,
                    myUserId: appState.currentUser?.id ?? "",
                    myRole: channel.myRole ?? "member",
                    isGlobalAdmin: appState.currentUser?.role == "admin",
                    onChanged: { Task { await vm.loadChannel(channelId: channelId) } }
                )
            }
        }
        .confirmationDialog(
            "Delete this message?",
            isPresented: Binding(
                get: { pendingMessageDelete != nil },
                set: { if !$0 { pendingMessageDelete = nil } }
            ),
            presenting: pendingMessageDelete,
        ) { msg in
            Button("Delete", role: .destructive) {
                let target = msg
                pendingMessageDelete = nil
                deleteMessage(target)
            }
            Button("Cancel", role: .cancel) { pendingMessageDelete = nil }
        } message: { _ in
            Text("This cannot be undone.")
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 0) {
                Text("# ")
                    .font(.system(size: 13))
                    .foregroundColor(appState.themeText.opacity(0.4))
                Text(vm.channel?.name.lowercased() ?? "")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.95))
                if let cat = vm.channel?.category, let parsed = ChannelCategory(rawValue: cat) {
                    Text(parsed.label)
                        .font(.system(size: 9, weight: .medium))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeText.opacity(0.08))
                        .foregroundColor(appState.themeText.opacity(0.55))
                        .cornerRadius(3)
                        .padding(.leading, 6)
                }
                Spacer()
                HStack(spacing: 6) {
                    if !vm.onlineUsers.isEmpty {
                        Text("●")
                            .font(.system(size: 8))
                            .foregroundColor(Color.matcha500)
                        Text("\(vm.onlineUsers.count) online")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.6))
                    }
                    if let count = vm.channel?.memberCount {
                        Text("·")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.25))
                        // Click → Manage members sheet. Visible to everyone
                        // (sheet itself adapts to role).
                        Button {
                            showManageMembers = true
                        } label: {
                            Text("\(count) members")
                                .font(.system(size: 10))
                                .foregroundColor(appState.themeText.opacity(0.4))
                                .underline(false)
                        }
                        .buttonStyle(.plain)
                        .help("Manage members")
                    }
                    // Live now badge — shown the moment we know a broadcast is
                    // active in this channel, regardless of whether THIS client
                    // has connected to the LiveKit feed yet. Sourced from
                    // BroadcastService.activeBroadcasts (WS + REST poll).
                    if broadcast.activeBroadcasts[channelId] != nil {
                        HStack(spacing: 3) {
                            Circle().fill(Color.red).frame(width: 5, height: 5)
                            Text("LIVE").font(.system(size: 9, weight: .bold)).foregroundColor(.red)
                        }
                    }
                    // Go Live button (owner only). "End" when this client is
                    // actively broadcasting OR when an active broadcast in this
                    // channel was started by the current user from another
                    // session (orphan recovery — quit app mid-stream, etc.).
                    if vm.channel?.myRole == "owner" {
                        let info = broadcast.activeBroadcasts[channelId]
                        let isOwnActive = info?.startedBy == appState.currentUser?.id && info != nil
                        let isLiveHere = broadcast.channelId == channelId && broadcast.isConnected
                        let showEnd = isLiveHere || isOwnActive
                        if showEnd {
                            Button {
                                Task {
                                    if isLiveHere {
                                        await broadcast.stopBroadcast()
                                    } else {
                                        await broadcast.endBroadcastForChannel(channelId: channelId)
                                    }
                                }
                            } label: {
                                HStack(spacing: 3) {
                                    Image(systemName: "stop.circle").font(.system(size: 10))
                                    Text("End").font(.system(size: 10, weight: .medium))
                                }
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(Color.red.opacity(0.2))
                                .foregroundColor(.red)
                                .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            .help("End the live broadcast")
                        } else {
                            // Pick mode at start time. Audio-only skips the
                            // camera grab entirely — useful when bandwidth
                            // is tight or the user just wants a voice call.
                            Menu {
                                Button {
                                    Task { await broadcast.startBroadcast(channelId: channelId, mode: .video) }
                                } label: {
                                    Label("Video call", systemImage: "video.fill")
                                }
                                Button {
                                    Task { await broadcast.startBroadcast(channelId: channelId, mode: .audio) }
                                } label: {
                                    Label("Audio only", systemImage: "waveform")
                                }
                            } label: {
                                HStack(spacing: 3) {
                                    Image(systemName: "video.badge.plus").font(.system(size: 10))
                                    Text("Go Live").font(.system(size: 10, weight: .medium))
                                }
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(appState.themeAccent.opacity(0.2))
                                .foregroundColor(appState.themeAccent)
                                .cornerRadius(4)
                            }
                            .menuStyle(.borderlessButton)
                            .menuIndicator(.hidden)
                            .fixedSize()
                            .help("Start a live broadcast — video or audio")
                        }
                    }
                    Button {
                        showInviteSheet = true
                    } label: {
                        HStack(spacing: 3) {
                            Image(systemName: "person.badge.plus").font(.system(size: 10))
                            Text("Invite").font(.system(size: 10, weight: .medium))
                        }
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(appState.themeAccent.opacity(0.2))
                        .foregroundColor(appState.themeAccent)
                        .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("Invite users to this channel")
                    if isAdmin {
                        Button {
                            appState.channelAdminWizardMode = .manage(channelId: channelId)
                            appState.showChannelAdminWizard = true
                        } label: {
                            Image(systemName: "questionmark.circle")
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeText.opacity(0.5))
                        }
                        .buttonStyle(.plain)
                        .help("Channel admin guide")
                    }
                }
            }
            if let desc = vm.channel?.description, !desc.isEmpty {
                Text(desc)
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeText.opacity(0.35))
                    .lineLimit(1)
                    .padding(.leading, 15)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial)
    }

    // MARK: - Watch-feed banner
    //
    // Shown above the messages list whenever an active broadcast exists in
    // this channel AND we're not currently connected to its LiveKit feed.
    // Replaces the silent auto-join — viewer always sees a "Live now" prompt
    // and clicks Watch to connect (covers the case where auto-join would have
    // failed token fetch / LiveKit connect with no UI feedback).

    private var watchFeedBanner: some View {
        let info = broadcast.activeBroadcasts[channelId]
        let starterName = info.flatMap { id in
            vm.onlineUsers.first(where: { $0.id == id.startedBy })?.name
        } ?? info?.title
        let title: String = {
            if let n = starterName { return "\(n) is live" }
            return "Live now in this channel"
        }()
        let hasErr = broadcast.errorMessage != nil
            && broadcast.channelId == channelId
            && !broadcast.isConnected

        return HStack(spacing: 10) {
            Circle().fill(Color.red).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.95))
                if hasErr, let msg = broadcast.errorMessage {
                    Text("Couldn't connect: \(msg)")
                        .font(.system(size: 10))
                        .foregroundColor(.red.opacity(0.85))
                        .lineLimit(2)
                }
            }
            Spacer()
            Button {
                Task { await broadcast.joinAsViewer(channelId: channelId) }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "play.circle.fill").font(.system(size: 11))
                    Text(hasErr ? "Retry" : "Watch feed").font(.system(size: 11, weight: .semibold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.red.opacity(0.85))
                .foregroundColor(.white)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color.red.opacity(0.12))
    }

    // MARK: - Messages

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(vm.messages, id: \.stableKey) { msg in
                        ChannelMessageRowView(
                            msg: msg,
                            members: vm.channel?.members ?? [],
                            currentUserId: appState.currentUser?.id ?? "",
                            isAdmin: isAdmin,
                            hoveredMessageId: $hoveredMessageId,
                            onReply: { replyingTo = $0 },
                            onToggleReaction: toggleReaction,
                            onRequestDelete: { pendingMessageDelete = $0 },
                            onRequestEdit: { editingMessage = $0; inputText = $0.content; replyingTo = nil },
                            onOpenAttachment: { previewFile = previewModel($0) },
                            onCreateTicket: vm.channel?.projectId != nil ? { startTicketDraft(from: $0) } : nil
                        )
                        .opacity((msg.pending || msg.failed) ? 0.55 : 1.0)
                        .id(msg.stableKey)
                    }
                    if !vm.typingUsers.isEmpty {
                        HStack(alignment: .center, spacing: 6) {
                            Spacer().frame(width: senderColumnWidth + 16)
                            TypingBubbleView()
                            Text(vm.typingUsers.values.sorted().joined(separator: ", "))
                                .font(.system(size: 10))
                                .foregroundColor(appState.themeText.opacity(0.35))
                        }
                        .transition(.opacity)
                    }
                    // Bottom sentinel — visible only when scrolled to the end.
                    // Gates auto-scroll so inbound messages don't yank the view
                    // down while the user reads history (macOS 14: no
                    // onScrollGeometryChange).
                    Color.clear
                        .frame(height: 1)
                        .id("__bottom_anchor")
                        .onAppear { isAtBottom = true }
                        .onDisappear { isAtBottom = false }
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            .onChange(of: vm.messages.count) {
                guard isAtBottom, let last = vm.messages.last else { return }
                withAnimation { proxy.scrollTo(last.stableKey, anchor: .bottom) }
            }
            // Our own send — always jump to the newest message regardless of
            // scroll position, so a reply reveals itself without a manual scroll.
            .onChange(of: selfSendScroll) {
                guard let last = vm.messages.last else { return }
                isAtBottom = true
                withAnimation { proxy.scrollTo(last.stableKey, anchor: .bottom) }
            }
            // Initial render scroll-to-bottom. .onChange above fires when
            // the REST load flips messages.count 0→N, but proxy.scrollTo
            // runs in the same SwiftUI commit as the LazyVStack's cell
            // build — the target id isn't tracked yet so the scroll
            // silently no-ops. A 50ms yield lets the cells materialise
            // first. Re-fires when the user switches channels.
            .task(id: vm.channel?.id) {
                try? await Task.sleep(for: .milliseconds(50))
                if let last = vm.messages.last {
                    proxy.scrollTo(last.stableKey, anchor: .bottom)
                }
            }
        }
        .overlay(
            Group {
                if isDragOver {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(appState.themeAccent, style: StrokeStyle(lineWidth: 2, dash: [6]))
                        .padding(8)
                        .overlay(
                            Text("drop files to attach")
                                .font(.system(size: 12))
                                .foregroundColor(appState.themeAccent)
                        )
                        .allowsHitTesting(false)
                }
            }
        )
        .onDrop(of: [UTType.fileURL], isTargeted: $isDragOver) { providers in
            handleFileDrop(providers)
            return true
        }
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
        .sheet(isPresented: $showTicketReview) {
            if let draft = ticketDraft, let pid = vm.channel?.projectId {
                AIDraftReviewSheet(
                    draft: draft,
                    collaborators: [],
                    elements: [],
                    onCreate: { title, column, priority, assignedTo, description, category, elementId, subtasks in
                        _ = try? await MatchaWorkService.shared.createProjectTask(
                            projectId: pid, title: title, boardColumn: column,
                            description: description, priority: priority,
                            assignedTo: assignedTo, category: category,
                            elementId: elementId, subtasks: subtasks
                        )
                    },
                    onClose: { showTicketReview = false; ticketDraft = nil }
                )
            }
        }
        .overlay(alignment: .top) {
            if draftingTicket {
                Label("Drafting ticket…", systemImage: "sparkles")
                    .font(.system(size: 11, weight: .medium))
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(.top, 8)
            } else if let err = ticketDraftError {
                Text(err)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(Color.red.opacity(0.85), in: Capsule())
                    .padding(.top, 8)
                    .onTapGesture { ticketDraftError = nil }
                    .task {
                        try? await Task.sleep(for: .seconds(4))
                        await MainActor.run { ticketDraftError = nil }
                    }
            }
        }
    }

    /// Turn a chat message into a kanban ticket: AI-draft it against the linked
    /// project, then open the review sheet. Project chats only (guarded by the
    /// caller passing onCreateTicket).
    private func startTicketDraft(from msg: ChannelMessage) {
        guard let pid = vm.channel?.projectId, !draftingTicket else { return }
        let text = msg.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draftingTicket = true
        ticketDraftError = nil
        Task {
            do {
                let draft = try await MatchaWorkService.shared.draftTaskFromPrompt(
                    projectId: pid, prompt: text, model: ticketDraftModel
                )
                await MainActor.run {
                    draftingTicket = false
                    ticketDraft = draft
                    showTicketReview = true
                }
            } catch {
                await MainActor.run {
                    draftingTicket = false
                    if case APIError.httpError(let code, _) = error, code == 429 {
                        ticketDraftError = "Daily AI limit reached — try again later."
                    } else {
                        ticketDraftError = "Couldn't draft a ticket from that message."
                    }
                }
            }
        }
    }

    /// Adapt a channel attachment to the shared in-app preview model. Lives at
    /// this level (not per-row) so the single hoisted sheet owns presentation.
    private func previewModel(_ att: ChannelAttachment) -> MWProjectFile {
        MWProjectFile(
            id: att.url, projectId: nil, taskId: nil, uploadedBy: nil,
            filename: att.filename, storageUrl: att.url,
            contentType: att.contentType, fileSize: att.size, createdAt: nil
        )
    }

    private func deleteMessage(_ msg: ChannelMessage) {
        Task {
            do {
                try await ChannelsService.shared.deleteMessage(channelId: channelId, messageId: msg.id)
                await MainActor.run {
                    if let idx = vm.messages.firstIndex(where: { $0.id == msg.id }) {
                        vm.messages[idx].deletedAt = ISO8601DateFormatter().string(from: Date())
                        vm.messages[idx].deletedBy = appState.currentUser?.id ?? ""
                    }
                }
            } catch {
                vm.errorMessage = "Delete failed: \(error.localizedDescription)"
            }
        }
    }

    private func toggleReaction(messageId: String, emoji: String) {
        Task {
            do {
                _ = try await ChannelsService.shared.toggleReaction(
                    channelId: channelId, messageId: messageId, emoji: emoji
                )
            } catch {
                vm.errorMessage = "Reaction failed: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Derived

    private var userHandle: String {
        let email = appState.currentUser?.email ?? "you"
        return email.split(separator: "@").first.map(String.init) ?? "you"
    }

    private var channelSlug: String {
        vm.channel?.slug ?? vm.channel?.name.lowercased().replacingOccurrences(of: " ", with: "-") ?? "channel"
    }

    // MARK: - Actions

    private func send() {
        let trimmed = inputText.trimmingCharacters(in: .whitespaces)
        // Edit mode: commit the edit instead of sending a new message.
        if let editing = editingMessage {
            editingMessage = nil
            inputText = ""
            guard !trimmed.isEmpty else { return }
            Task { await vm.editMessage(editing, newContent: trimmed) }
            return
        }
        // Weave in a referenced kanban ticket (from "Chat about this ticket")
        // as a reply-style prefix so the channel message carries the ticket
        // context. Captured + cleared on send.
        var content = trimmed
        if let ref = appState.pendingTicketRef {
            let colLabel = ref.column.replacingOccurrences(of: "_", with: " ").capitalized
            // Machine-readable marker the message row renders as a clickable
            // ticket chip. Sanitize the title of the delimiter chars so it
            // round-trips; clients that don't parse it just see the raw text.
            let safeTitle = ref.title
                .replacingOccurrences(of: "⟦", with: "")
                .replacingOccurrences(of: "⟧", with: "")
                .replacingOccurrences(of: "|", with: "/")
            let token = "⟦ticket:\(ref.id)|\(safeTitle)|\(colLabel)⟧"
            content = trimmed.isEmpty ? token : "\(token)\n\(trimmed)"
            appState.pendingTicketRef = nil
        }
        let attachmentsToSend = pendingAttachments
        guard !content.isEmpty || !attachmentsToSend.isEmpty else { return }
        guard !isUploading else { return }

        let replyId = replyingTo?.id
        let replyPreviewForOptimistic = replyingTo.map { ReplyPreview(
            id: $0.id,
            senderName: $0.senderName,
            content: $0.content,
            attachments: $0.attachments,
        ) }

        if attachmentsToSend.isEmpty {
            let cmid = UUID().uuidString
            appendOptimisticMessage(
                clientMessageId: cmid,
                content: content,
                attachments: [],
                replyToId: replyId,
                replyPreview: replyPreviewForOptimistic,
            )
            ws.sendMessage(channelId: channelId, content: content, replyToId: replyId, clientMessageId: cmid)
            inputText = ""
            replyingTo = nil
            selfSendScroll += 1
            return
        }

        isUploading = true
        Task {
            do {
                let files = attachmentsToSend.map { (data: $0.data, filename: $0.filename, mimeType: $0.mimeType) }
                let uploaded = try await ChannelsService.shared.uploadAttachments(
                    channelId: channelId, files: files
                )
                await MainActor.run {
                    let cmid = UUID().uuidString
                    appendOptimisticMessage(
                        clientMessageId: cmid,
                        content: content,
                        attachments: uploaded,
                        replyToId: replyId,
                        replyPreview: replyPreviewForOptimistic,
                    )
                    ws.sendMessage(channelId: channelId, content: content, attachments: uploaded, replyToId: replyId, clientMessageId: cmid)
                    inputText = ""
                    replyingTo = nil
                    pendingAttachments.removeAll()
                    isUploading = false
                    selfSendScroll += 1
                }
            } catch {
                await MainActor.run {
                    vm.errorMessage = "Upload failed: \(error.localizedDescription)"
                    isUploading = false
                }
            }
        }
    }

    private func appendOptimisticMessage(
        clientMessageId: String,
        content: String,
        attachments: [ChannelAttachment],
        replyToId: String?,
        replyPreview: ReplyPreview?,
    ) {
        guard let me = appState.currentUser else { return }
        let pending = ChannelMessage(
            id: clientMessageId,
            channelId: channelId,
            senderId: me.id,
            senderName: me.name ?? me.email,
            senderAvatarUrl: me.avatarUrl,
            content: content,
            attachments: attachments,
            replyToId: replyToId,
            replyPreview: replyPreview,
            reactions: [],
            createdAt: ISO8601DateFormatter().string(from: Date()),
            editedAt: nil,
            mentionedUserIds: nil,
            clientMessageId: clientMessageId,
            pending: true,
        )
        vm.messages.append(pending)
        vm.schedulePendingTimeout(clientMessageId: clientMessageId)
    }

    // MARK: - File picker + drop

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsOtherFileTypes = true   // allow any type; validated on ingest
        if panel.runModal() == .OK {
            for url in panel.urls {
                ingestFile(at: url)
            }
        }
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier) { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                Task { @MainActor in ingestFile(at: url) }
            }
        }
    }

    private func ingestFile(at url: URL) {
        let ext = url.pathExtension.lowercased()
        guard !blockedExtensions.contains(ext) else {
            vm.errorMessage = "File type .\(ext) isn't allowed"
            return
        }
        guard pendingAttachments.count < maxAttachments else {
            vm.errorMessage = "Max \(maxAttachments) attachments per message"
            return
        }
        guard let data = try? Data(contentsOf: url) else {
            vm.errorMessage = "Could not read \(url.lastPathComponent)"
            return
        }
        guard data.count <= maxAttachmentBytes else {
            vm.errorMessage = "\(url.lastPathComponent) is too large (max 50 MB)"
            return
        }
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
        pendingAttachments.append(
            PendingChannelAttachment(data: data, filename: url.lastPathComponent, mimeType: mime)
        )
    }

    /// Pull an image off the system clipboard and stage it as an attachment.
    /// Lets the user screenshot to clipboard (⌃⌘⇧4) and paste straight into the
    /// composer — no desktop-file roundtrip. Sandbox-safe (no permission).
    private func pasteImageFromClipboard() {
        let pb = NSPasteboard.general
        // Prefer PNG; fall back to TIFF (the format screenshots land in) and
        // transcode to PNG so the upload is consistently image/png.
        let data: Data
        if let png = pb.data(forType: .png) {
            data = png
        } else if let tiff = pb.data(forType: .tiff),
                  let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) {
            data = png
        } else {
            vm.errorMessage = "No image on the clipboard — screenshot with ⌃⌘⇧4 first"
            return
        }
        guard pendingAttachments.count < maxAttachments else {
            vm.errorMessage = "Max \(maxAttachments) attachments per message"
            return
        }
        guard data.count <= maxAttachmentBytes else {
            vm.errorMessage = "Pasted image is too large (max 10 MB)"
            return
        }
        let stamp = Int(Date().timeIntervalSince1970)
        pendingAttachments.append(
            PendingChannelAttachment(data: data, filename: "pasted-\(stamp).png", mimeType: "image/png")
        )
    }
}

// MARK: - Typing bubble

private struct TypingBubbleView: View {
    @State private var phase: Int = 0

    private let dotSize: CGFloat = 5
    private let dotColor = Color.borderColor

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(dotColor)
                    .frame(width: dotSize, height: dotSize)
                    .scaleEffect(phase == i ? 1.4 : 0.8)
                    .animation(
                        .easeInOut(duration: 0.4)
                            .repeatForever(autoreverses: true)
                            .delay(Double(i) * 0.15),
                        value: phase
                    )
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(Color.cardBackground)
        .cornerRadius(10)
        .onAppear {
            phase = 0
            withAnimation { phase = 2 }
        }
    }
}
