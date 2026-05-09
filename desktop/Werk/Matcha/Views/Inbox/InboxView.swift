import SwiftUI

struct InboxView: View {
    @State private var conversations: [MWInboxConversation] = []
    @State private var selectedId: String?
    @State private var activeConversation: MWInboxConversationDetail?
    @State private var isLoading = true
    @State private var threadLoading = false
    @State private var showCompose = false
    @State private var currentUserId: String = ""
    @Environment(AppState.self) private var appState

    var body: some View {
        HSplitView {
            // Conversation list
            VStack(spacing: 0) {
                HStack {
                    Text("Inbox")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button { showCompose = true } label: {
                        Image(systemName: "square.and.pencil")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)

                Divider().opacity(0.3)

                if isLoading {
                    Spacer()
                    ProgressView().tint(.secondary)
                    Spacer()
                } else if conversations.isEmpty {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "envelope")
                            .font(.system(size: 28))
                            .foregroundColor(.secondary)
                        Text("No messages")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                } else {
                    List(conversations, selection: $selectedId) { convo in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                let others = convo.participants?.filter { $0.userId != currentUserId } ?? []
                                Text(convo.title ?? others.map(\.name).joined(separator: ", "))
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.white)
                                    .lineLimit(1)
                                Spacer()
                                if (convo.unreadCount ?? 0) > 0 {
                                    Circle().fill(Color.matcha500).frame(width: 8, height: 8)
                                }
                            }
                            if let preview = convo.lastMessagePreview {
                                Text(preview)
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                            }
                        }
                        .padding(.vertical, 2)
                        .tag(convo.id)
                    }
                    .listStyle(.sidebar)
                    .scrollContentBackground(.hidden)
                }
            }
            .frame(minWidth: 220, maxWidth: 280)
            .background(Color.appBackground)

            // Message thread
            if threadLoading {
                ZStack { Color.appBackground; ProgressView().tint(.secondary) }
            } else if let convo = activeConversation {
                InboxThreadView(conversation: convo, currentUserId: currentUserId, onSend: { content, files in
                    let msg = try await InboxService.shared.sendMessage(conversationId: convo.id, content: content, files: files)
                    await MainActor.run {
                        activeConversation?.messages?.append(msg)
                    }
                })
            } else {
                ZStack {
                    Color.appBackground
                    VStack(spacing: 8) {
                        Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 36)).foregroundColor(.secondary)
                        Text("Select a conversation").font(.system(size: 13)).foregroundColor(.secondary)
                    }
                }
            }
        }
        .background(Color.appBackground)
        .onChange(of: selectedId) {
            guard let id = selectedId else { return }
            threadLoading = true
            Task {
                do {
                    let detail = try await InboxService.shared.getConversation(id: id)
                    await MainActor.run { activeConversation = detail; threadLoading = false }
                } catch {
                    await MainActor.run { threadLoading = false }
                }
            }
        }
        .task {
            currentUserId = appState.currentUser?.id ?? ""
            await loadConversations()
        }
        .sheet(isPresented: $showCompose) {
            InboxComposeView(currentUserId: currentUserId) { convo in
                conversations.insert(MWInboxConversation(
                    id: convo.id, title: convo.title, isGroup: convo.isGroup,
                    lastMessageAt: convo.lastMessageAt, lastMessagePreview: convo.lastMessagePreview,
                    participants: convo.participants, unreadCount: 0
                ), at: 0)
                selectedId = convo.id
                showCompose = false
            }
        }
    }

    private func loadConversations() async {
        do {
            let list = try await InboxService.shared.listConversations()
            await MainActor.run { conversations = list; isLoading = false }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}

// MARK: - Thread View

struct InboxThreadView: View {
    let conversation: MWInboxConversationDetail
    let currentUserId: String
    let onSend: (String, [(data: Data, filename: String, mimeType: String)]?) async throws -> Void

    @State private var draft = ""
    @State private var isSending = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                let others = conversation.participants?.filter { $0.userId != currentUserId } ?? []
                Text(conversation.title ?? others.map(\.name).joined(separator: ", "))
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                if conversation.isGroup == true {
                    Text("\(conversation.participants?.count ?? 0) participants")
                        .font(.system(size: 10)).foregroundColor(.secondary)
                }
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider().opacity(0.3)

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(conversation.messages ?? []) { msg in
                            let isMine = msg.senderId == currentUserId
                            HStack {
                                if isMine { Spacer() }
                                VStack(alignment: isMine ? .trailing : .leading, spacing: 2) {
                                    if conversation.isGroup == true && !isMine {
                                        Text(msg.senderName)
                                            .font(.system(size: 9))
                                            .foregroundColor(.secondary)
                                    }
                                    VStack(alignment: .leading, spacing: 4) {
                                        if !msg.content.isEmpty {
                                            Text(msg.content)
                                                .font(.system(size: 13))
                                                .foregroundColor(isMine ? .white : Color(.labelColor))
                                        }
                                        // Attachments
                                        if let attachments = msg.attachments, !attachments.isEmpty {
                                            ForEach(attachments) { att in
                                                if att.isImage {
                                                    AsyncImage(url: URL(string: att.url)) { phase in
                                                        if let img = phase.image {
                                                            img.resizable().scaledToFit().frame(maxWidth: 200, maxHeight: 150).cornerRadius(8)
                                                        } else {
                                                            ProgressView().frame(width: 80, height: 60)
                                                        }
                                                    }
                                                } else {
                                                    Link(destination: URL(string: att.url) ?? URL(string: "about:blank")!) {
                                                        HStack(spacing: 4) {
                                                            Image(systemName: "doc").font(.system(size: 10))
                                                            Text(att.filename).font(.system(size: 10)).lineLimit(1)
                                                        }
                                                        .padding(.horizontal, 8).padding(.vertical, 4)
                                                        .background(Color.secondary.opacity(0.15))
                                                        .cornerRadius(6)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(isMine ? Color.matcha600.opacity(0.6) : Color.zinc800)
                                    .cornerRadius(16)
                                    .frame(maxWidth: 320, alignment: isMine ? .trailing : .leading)

                                    Text(formatInboxTime(msg.createdAt))
                                        .font(.system(size: 9))
                                        .foregroundColor(.secondary)
                                }
                                if !isMine { Spacer() }
                            }
                            .id(msg.id)
                        }
                    }
                    .padding(16)
                }
                .onChange(of: conversation.messages?.count) {
                    if let lastId = conversation.messages?.last?.id {
                        withAnimation { proxy.scrollTo(lastId, anchor: .bottom) }
                    }
                }
            }

            Divider().opacity(0.3)

            // Input
            HStack(spacing: 8) {
                TextField("Message...", text: $draft)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .onSubmit { send() }

                Button { send() } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 24))
                        .foregroundColor(draft.isEmpty ? .secondary : .matcha500)
                }
                .buttonStyle(.plain)
                .disabled(draft.isEmpty || isSending)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
        }
        .background(Color.appBackground)
    }

    private func send() {
        let content = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !isSending else { return }
        draft = ""
        isSending = true
        Task {
            try? await onSend(content, nil)
            await MainActor.run { isSending = false }
        }
    }
}

private func formatInboxTime(_ iso: String) -> String {
    guard let date = parseMWDate(iso) else { return iso }
    return date.formatted(date: .omitted, time: .shortened)
}
