import SwiftUI

/// A single channel's real-time chat. Drives the shared `ChannelChatViewModel`
/// (history load + WS reconcile) and owns the optimistic-send path, mirroring
/// the macOS `ChannelDetailView` contract: build a `pending` message keyed by a
/// client_message_id, append it, schedule the failure timeout, then send over
/// the socket — the VM swaps in the server echo when it arrives.
struct ChannelChatView: View {
    let channel: ChannelSummary
    @Environment(AppState.self) private var appState
    @Environment(CallService.self) private var call
    @Environment(BroadcastService.self) private var broadcast

    @State private var vm = ChannelChatViewModel()
    @State private var showCall = false
    @State private var showBroadcast = false
    @State private var text = ""
    @State private var replyingTo: ChannelMessage?
    @State private var attachments: [PendingAttachment] = []
    @State private var isUploading = false
    @State private var editing: ChannelMessage?
    @State private var editText = ""
    @State private var lastTypingSent = Date.distantPast

    private let ws = ChannelsWebSocket.shared
    private let service = ChannelsService.shared
    private let bottomID = "chat-bottom"

    private var myUserId: String { appState.currentUser?.id ?? "" }

    var body: some View {
        VStack(spacing: 0) {
            liveBar
            messageList
            if !vm.typingUsers.isEmpty { typingBar }
        }
        .safeAreaInset(edge: .bottom) {
            MessageComposer(
                text: $text, replyingTo: $replyingTo, attachments: $attachments,
                isUploading: isUploading, onSend: send, onTyping: handleTyping
            )
        }
        .navigationTitle(channel.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                callButton
                broadcastButton
                presence
            }
        }
        .task { await vm.resume(channelId: channel.id) }
        .task {
            await call.fetchCallStatus(channelId: channel.id)
            await broadcast.fetchBroadcastStatus(channelId: channel.id)
        }
        .onAppear { appState.selectedChannelId = channel.id }
        .onDisappear {
            appState.selectedChannelId = nil
            vm.stop(channelId: channel.id)
        }
        .onChange(of: call.isConnected) { _, connected in
            showCall = connected && call.channelId == channel.id
        }
        .onChange(of: broadcast.isConnected) { _, connected in
            showBroadcast = connected && broadcast.channelId == channel.id
        }
        .fullScreenCover(isPresented: $showCall) {
            CallView(channelName: channel.name, members: vm.channel?.members ?? [])
                .environment(call)
        }
        .fullScreenCover(isPresented: $showBroadcast) {
            BroadcastView(channelName: channel.name, members: vm.channel?.members ?? [])
                .environment(broadcast)
        }
        .alert("Edit message", isPresented: editingPresented) {
            TextField("Message", text: $editText)
            Button("Cancel", role: .cancel) { editing = nil }
            Button("Save", action: commitEdit)
        }
        .overlay(alignment: .top) {
            if let err = vm.errorMessage {
                Text(err).font(.caption).padding(8)
                    .background(.red.opacity(0.9), in: Capsule())
                    .foregroundStyle(.white).padding(.top, 4)
            }
        }
    }

    // MARK: - Message list

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    if vm.isLoading {
                        ProgressView().padding(.vertical, 24)
                    }
                    ForEach(vm.messages) { msg in
                        MessageRow(
                            message: msg, currentUserId: myUserId,
                            onReply: { replyingTo = $0 },
                            onToggleReaction: toggleReaction,
                            onEdit: startEdit,
                            onDelete: deleteMessage,
                            onRetry: retry
                        )
                        .id(msg.stableKey)
                    }
                    Color.clear.frame(height: 1).id(bottomID)
                }
                .padding(.vertical, 8)
            }
            .onChange(of: vm.messages.count) {
                withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(bottomID, anchor: .bottom) }
            }
            .onChange(of: vm.isLoading) { _, loading in
                if !loading { proxy.scrollTo(bottomID, anchor: .bottom) }
            }
        }
    }

    private var typingBar: some View {
        HStack(spacing: 6) {
            ProgressView().controlSize(.mini)
            Text(typingText).font(.caption).foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.horizontal, 16).padding(.vertical, 4)
    }

    private var typingText: String {
        let names = vm.typingUsers.values.map { $0.replacingOccurrences(of: "_", with: " ") }
        switch names.count {
        case 0: return ""
        case 1: return "\(names[0].capitalized) is typing…"
        default: return "Several people are typing…"
        }
    }

    private var presence: some View {
        HStack(spacing: 3) {
            Circle().fill(.green).frame(width: 7, height: 7)
            Text("\(max(vm.onlineUsers.count, 1))").font(.caption.monospacedDigit())
        }
        .foregroundStyle(.secondary)
    }

    // MARK: - Send (optimistic)

    private func send() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let toSend = attachments
        guard !trimmed.isEmpty || !toSend.isEmpty, !isUploading else { return }

        let replyId = replyingTo?.id
        let replyPreview = replyingTo.map {
            ReplyPreview(id: $0.id, senderName: $0.senderName, content: $0.content, attachments: $0.attachments)
        }

        if toSend.isEmpty {
            let cmid = UUID().uuidString
            appendOptimistic(cmid: cmid, content: trimmed, attachments: [], replyId: replyId, replyPreview: replyPreview)
            ws.sendMessage(channelId: channel.id, content: trimmed, replyToId: replyId, clientMessageId: cmid)
            resetComposer()
            return
        }

        isUploading = true
        Task {
            do {
                let files = toSend.map { (data: $0.data, filename: $0.filename, mimeType: $0.mimeType) }
                let uploaded = try await service.uploadAttachments(channelId: channel.id, files: files)
                await MainActor.run {
                    let cmid = UUID().uuidString
                    appendOptimistic(cmid: cmid, content: trimmed, attachments: uploaded, replyId: replyId, replyPreview: replyPreview)
                    ws.sendMessage(channelId: channel.id, content: trimmed, attachments: uploaded, replyToId: replyId, clientMessageId: cmid)
                    isUploading = false
                    resetComposer()
                }
            } catch {
                await MainActor.run {
                    vm.errorMessage = "Upload failed: \(error.localizedDescription)"
                    isUploading = false
                }
            }
        }
    }

    private func appendOptimistic(cmid: String, content: String, attachments: [ChannelAttachment],
                                  replyId: String?, replyPreview: ReplyPreview?) {
        guard let me = appState.currentUser else { return }
        let pending = ChannelMessage(
            id: cmid, channelId: channel.id, senderId: me.id,
            senderName: me.name ?? me.email, senderAvatarUrl: me.avatarUrl,
            content: content, attachments: attachments,
            replyToId: replyId, replyPreview: replyPreview, reactions: [],
            createdAt: ISO8601DateFormatter().string(from: Date()), editedAt: nil,
            mentionedUserIds: nil, clientMessageId: cmid, pending: true
        )
        vm.messages.append(pending)
        vm.schedulePendingTimeout(clientMessageId: cmid)
    }

    private func resetComposer() {
        text = ""
        replyingTo = nil
        attachments = []
    }

    // MARK: - Actions

    private func toggleReaction(_ msg: ChannelMessage, _ emoji: String) {
        guard !msg.pending, !msg.failed else { return }
        Task { try? await service.toggleReaction(channelId: channel.id, messageId: msg.id, emoji: emoji) }
    }

    private func deleteMessage(_ msg: ChannelMessage) {
        guard !msg.pending else { return }
        Task { try? await service.deleteMessage(channelId: channel.id, messageId: msg.id) }
    }

    private func startEdit(_ msg: ChannelMessage) {
        editing = msg
        editText = msg.content
    }

    private func commitEdit() {
        guard let e = editing else { return }
        let newText = editText
        editing = nil
        Task { await vm.editMessage(e, newContent: newText) }
    }

    private func retry(_ msg: ChannelMessage) {
        guard let cmid = msg.clientMessageId else { return }
        if let i = vm.messages.firstIndex(where: { $0.id == msg.id }) {
            vm.messages[i].failed = false
            vm.messages[i].pending = true
        }
        ws.sendMessage(channelId: channel.id, content: msg.content, attachments: msg.attachments,
                       replyToId: msg.replyToId, clientMessageId: cmid)
        vm.schedulePendingTimeout(clientMessageId: cmid)
    }

    private func handleTyping() {
        let now = Date()
        guard now.timeIntervalSince(lastTypingSent) > 2 else { return }
        lastTypingSent = now
        ws.sendTyping(channelId: channel.id)
    }

    private var editingPresented: Binding<Bool> {
        Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })
    }

    // MARK: - Calls / broadcast

    /// Join banners shown above the timeline when a call/broadcast is live in
    /// this channel and we're not already in it.
    @ViewBuilder
    private var liveBar: some View {
        if call.activeCalls[channel.id] != nil, !(call.isConnected && call.channelId == channel.id) {
            Button { Task { await call.joinCall(channelId: channel.id) } } label: {
                Label("Call in progress · Tap to join", systemImage: "phone.fill")
                    .font(.caption.weight(.medium))
                    .frame(maxWidth: .infinity).padding(8)
            }
            .tint(.green)
            .background(.green.opacity(0.12))
        }
        if broadcast.activeBroadcasts[channel.id] != nil,
           !(broadcast.isConnected && broadcast.channelId == channel.id) {
            Button { Task { await broadcast.joinAsViewer(channelId: channel.id) } } label: {
                Label("Live now · Watch", systemImage: "dot.radiowaves.left.and.right")
                    .font(.caption.weight(.medium))
                    .frame(maxWidth: .infinity).padding(8)
            }
            .tint(.red)
            .background(.red.opacity(0.12))
        }
    }

    @ViewBuilder
    private var callButton: some View {
        if call.activeCalls[channel.id] != nil {
            Button { Task { await call.joinCall(channelId: channel.id) } } label: {
                Image(systemName: "phone.fill").foregroundStyle(.green)
            }
        } else if appState.isPlusActive {
            Button { Task { await call.startCall(channelId: channel.id, mode: .members) } } label: {
                Image(systemName: "phone")
            }
        }
    }

    @ViewBuilder
    private var broadcastButton: some View {
        if broadcast.activeBroadcasts[channel.id] != nil {
            Button { Task { await broadcast.joinAsViewer(channelId: channel.id) } } label: {
                Image(systemName: "dot.radiowaves.left.and.right").foregroundStyle(.red)
            }
        } else if appState.isPlusActive {
            Button { Task { await broadcast.startBroadcast(channelId: channel.id) } } label: {
                Image(systemName: "video")
            }
        }
    }
}
