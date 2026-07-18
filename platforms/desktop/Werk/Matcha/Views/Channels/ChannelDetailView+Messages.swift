import SwiftUI
import AppKit
import UniformTypeIdentifiers

extension ChannelDetailView {
    // MARK: - Watch-feed banner
    //
    // Shown above the messages list whenever an active broadcast exists in
    // this channel AND we're not currently connected to its LiveKit feed.
    // Replaces the silent auto-join — viewer always sees a "Live now" prompt
    // and clicks Watch to connect (covers the case where auto-join would have
    // failed token fetch / LiveKit connect with no UI feedback).

    var watchFeedBanner: some View {
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

    // MARK: - Call join banner
    //
    // Shown above the messages list when an active audio call exists in this
    // channel and we're not connected to it. Join is gated by the call's
    // policy: members-mode admits anyone, invite-only needs an invite (the
    // owner always may). Disabled with a "full" label at 4/4.

    var callJoinBanner: some View {
        let info = call.activeCalls[channelId]
        let myId = appState.currentUser?.id ?? ""
        let starterName = info.flatMap { i in
            vm.channel?.members.first(where: { $0.userId == i.startedBy })?.name
        }
        let title = starterName.map { "\($0) started an audio call" } ?? "Audio call in progress"
        let count = info?.participantIds.count ?? 0
        let isFull = count >= call.maxParticipants
        let mayJoin: Bool = {
            guard let i = info else { return false }
            if i.startedBy == myId { return true }
            if i.mode == .members { return true }
            return i.invitedUserIds.contains(myId)
        }()
        let hasErr = call.errorMessage != nil
            && call.channelId == channelId
            && !call.isConnected

        return HStack(spacing: 10) {
            Image(systemName: "waveform")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(Color.matcha500)
            VStack(alignment: .leading, spacing: 1) {
                Text("\(title) · \(count)/\(call.maxParticipants)")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.95))
                if hasErr, let msg = call.errorMessage {
                    Text("Couldn't connect: \(msg)")
                        .font(.system(size: 10))
                        .foregroundColor(.red.opacity(0.85))
                        .lineLimit(2)
                } else if !mayJoin {
                    Text("Invite only — ask the channel owner for an invite")
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeText.opacity(0.45))
                }
            }
            Spacer()
            if mayJoin {
                Button {
                    Task { await call.joinCall(channelId: channelId) }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "phone.fill").font(.system(size: 11))
                        Text(hasErr ? "Retry" : (isFull ? "Full" : "Join"))
                            .font(.system(size: 11, weight: .semibold))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(isFull ? Color.zinc800 : Color.matcha600)
                    .foregroundColor(.white)
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
                .disabled(isFull && !hasErr)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color.matcha600.opacity(0.12))
    }

    // MARK: - Messages

    var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if vm.hasMoreHistory {
                        Button {
                            guard let anchor = vm.messages.first?.stableKey else { return }
                            Task {
                                await vm.loadOlder()
                                // Nothing prepended (failure or end of history)
                                // → don't jump the viewport.
                                guard vm.messages.first?.stableKey != anchor else { return }
                                // Pin the previously-oldest row to the top so the
                                // reader's position is preserved after older rows
                                // prepend (50ms yield lets the cells materialise,
                                // same pattern as the initial-load scroll below).
                                try? await Task.sleep(for: .milliseconds(50))
                                proxy.scrollTo(anchor, anchor: .top)
                            }
                        } label: {
                            Group {
                                if vm.isLoadingOlder {
                                    ProgressView().controlSize(.small)
                                } else {
                                    Text("Load earlier messages")
                                        .font(.system(size: 11, weight: .medium))
                                        .foregroundColor(appState.themeAccent)
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                        }
                        .buttonStyle(.plain)
                        .disabled(vm.isLoadingOlder)
                    }
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
                            onRequestEdit: { editingMessage = $0; seedComposer($0.content); replyingTo = nil },
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
            // Always follow new messages to the bottom. The previous isAtBottom
            // gate was unreliable (the lazy bottom sentinel's appear/disappear
            // mis-fires), so inbound messages often didn't reposition the view
            // and the newest message sat off-screen. Chat-standard behavior:
            // a new message always reveals itself.
            // Follow new messages to the bottom, but key on the LAST message's
            // identity rather than messages.count — otherwise paging in older
            // history (which grows the count from the top) would yank the view
            // to the bottom. A prepend leaves `last` unchanged, so it won't fire.
            .onChange(of: vm.messages.last?.stableKey) {
                guard let last = vm.messages.last else { return }
                withAnimation { proxy.scrollTo(last.stableKey, anchor: .bottom) }
            }
            // Refresh-merge case the trigger above can't see: messages arrived
            // while away but a pending/failed row is stuck at the tail, so the
            // last identity is unchanged. The VM bumps this tick whenever a
            // silent merge changes the list.
            .onChange(of: vm.scrollToLatestTick) {
                guard let last = vm.messages.last else { return }
                withAnimation { proxy.scrollTo(last.stableKey, anchor: .bottom) }
            }
            // Belt-and-suspenders for our own send (the count may not change at
            // the exact commit the optimistic row lands).
            .onChange(of: selfSendScroll) {
                guard let last = vm.messages.last else { return }
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
}
