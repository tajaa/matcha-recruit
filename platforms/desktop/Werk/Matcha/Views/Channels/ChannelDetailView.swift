import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ChannelDetailView: View {
    let channelId: String
    /// True when shown inside a collab project's chat panel. Embedded
    /// channels must NOT claim the workspace-tab active context — the
    /// enclosing project owns it (otherwise the collab project can't be pinned).
    var isEmbedded: Bool = false

    @Environment(AppState.self) var appState
    @State var vm = ChannelChatViewModel()
    /// Composer draft seed. The composer owns the live text locally (so typing
    /// doesn't re-render this view + the message list); we push values in by
    /// bumping the nonce — to prefill on "edit message" or clear after send.
    @State var composerSeed = ""
    @State var composerSeedNonce = 0

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
    @State var pendingAttachments: [PendingChannelAttachment] = []
    @State var isUploading = false
    @State var isDragOver = false
    @State var replyingTo: ChannelMessage? = nil
    @State var hoveredMessageId: String? = nil
    @State var lastTypingSentAt: Date = .distantPast
    @State var showInviteSheet = false
    @State var showManageMembers = false
    @State var pendingMessageDelete: ChannelMessage? = nil
    /// When set, the composer is editing this message instead of sending new.
    @State var editingMessage: ChannelMessage? = nil
    @State var inviteToast: String?
    /// Single hoisted attachment-preview target. Lives here (not per-row) so a
    /// streaming message / hover re-render or LazyVStack recycle can't drop the
    /// binding mid-present — that was the flaky-open bug.
    @State var previewFile: MWProjectFile?
    // "Create ticket" from a message → AI draft → review sheet (project chats only).
    @State var ticketDraft: MWTaskDraft?
    @State var showTicketReview = false
    @State var draftingTicket = false
    @State var ticketDraftError: String?
    /// True while the bottom sentinel is on screen — gates message auto-scroll.
    @State var isAtBottom = true
    /// Bumped whenever WE send a message, to force the viewport to the newest
    /// message regardless of scroll position — sending a reply should always
    /// reveal your own message without a manual scroll.
    @State var selfSendScroll = 0
    // Chat → ticket always drafts with Flash Lite (cheap/fast for this
    // lightweight action), regardless of the header model selector.
    var ticketDraftModel: String? {
        mwModelOptions.first { $0.id == "flash-lite" }?.value
    }

    @Environment(BroadcastService.self) var broadcast: BroadcastService
    @Environment(CallService.self) var call: CallService

    var isAdmin: Bool {
        let role = vm.channel?.myRole ?? ""
        let global = appState.currentUser?.role ?? ""
        return role == "owner" || role == "moderator" || global == "admin"
    }

    let ws = ChannelsWebSocket.shared
    let senderColumnWidth: CGFloat = 160
    let maxAttachments = 10
    let maxAttachmentBytes = 50 * 1024 * 1024
    /// Permissive: block only executable / installer types; everything else
    /// (docs, markdown, code, images, video, audio, archives, …) is allowed.
    let blockedExtensions: Set<String> = [
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
                } else if call.channelId == channelId && call.isConnected {
                    // Audio call panel — server guarantees a channel never has
                    // a call and a broadcast active at once.
                    CallPanelView(
                        channelId: channelId,
                        channelName: vm.channel?.name ?? "channel",
                        isOwner: call.isOwner || vm.channel?.myRole == "owner",
                        members: vm.channel?.members ?? [],
                        myUserId: appState.currentUser?.id ?? "",
                    )
                        .environment(call)
                    Divider()
                } else if call.activeCalls[channelId] != nil {
                    callJoinBanner
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
                    onSend: { send($0) },
                    onOpenFilePicker: openFilePicker,
                    onPasteImage: pasteImageFromClipboard,
                    seed: composerSeed,
                    seedNonce: composerSeedNonce,
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
            await call.fetchCallStatus(channelId: channelId)
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

    var header: some View {
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
                    // Call pill — active audio call with live occupancy (n/4),
                    // sourced from CallService.activeCalls (WS + REST poll).
                    if let callInfo = call.activeCalls[channelId] {
                        HStack(spacing: 3) {
                            Image(systemName: "waveform")
                                .font(.system(size: 8, weight: .bold))
                            Text("CALL \(callInfo.participantIds.count)/\(call.maxParticipants)")
                                .font(.system(size: 9, weight: .bold))
                        }
                        .foregroundColor(Color.matcha500)
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
                        let callInfo = call.activeCalls[channelId]
                        let isCallHere = call.channelId == channelId && call.isConnected
                        if callInfo != nil || isCallHere {
                            // Calls are owner-started, so an active call in an
                            // owned channel is endable from here even when this
                            // client isn't connected (orphan path — quit the
                            // app mid-call and came back).
                            Button {
                                Task {
                                    if isCallHere {
                                        await call.stopCall()
                                    } else {
                                        await call.endCallForChannel(channelId: channelId)
                                    }
                                }
                            } label: {
                                HStack(spacing: 3) {
                                    Image(systemName: "phone.down.fill").font(.system(size: 10))
                                    Text("End call").font(.system(size: 10, weight: .medium))
                                }
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(Color.red.opacity(0.2))
                                .foregroundColor(.red)
                                .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            .help("End the audio call")
                        } else if showEnd {
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
                        } else if !appState.canGoLive {
                            // Go Live + calls are Pro/Business — locked chip
                            // opens the paywall (server gates both start
                            // endpoints regardless).
                            Button {
                                appState.presentPaywall(for: "go_live")
                            } label: {
                                HStack(spacing: 3) {
                                    Image(systemName: "lock.fill").font(.system(size: 9))
                                    Text("Go Live").font(.system(size: 10, weight: .medium))
                                }
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(appState.themeText.opacity(0.08))
                                .foregroundColor(appState.themeTextSecondary)
                                .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            .help("Going live needs Werk Pro")
                            Button {
                                appState.presentPaywall(for: "go_live")
                            } label: {
                                HStack(spacing: 3) {
                                    Image(systemName: "lock.fill").font(.system(size: 9))
                                    Text("Call").font(.system(size: 10, weight: .medium))
                                }
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(appState.themeText.opacity(0.08))
                                .foregroundColor(appState.themeTextSecondary)
                                .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            .help("Audio calls need Werk Pro")
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
                            // 4-person audio call. Join policy is picked here
                            // at start time; invite-only owners add people via
                            // the panel's Invite button after starting.
                            Menu {
                                Button {
                                    Task { await call.startCall(channelId: channelId, mode: .members) }
                                } label: {
                                    Label("All members can join", systemImage: "person.3.fill")
                                }
                                Button {
                                    Task { await call.startCall(channelId: channelId, mode: .inviteOnly) }
                                } label: {
                                    Label("Invite only", systemImage: "person.crop.circle.badge.checkmark")
                                }
                            } label: {
                                HStack(spacing: 3) {
                                    Image(systemName: "phone.badge.waveform.fill").font(.system(size: 10))
                                    Text("Call").font(.system(size: 10, weight: .medium))
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
                            .help("Start a 4-person audio call — open to members or invite-only")
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
}
