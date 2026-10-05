import SwiftUI

struct InboxListView: View {
    @Environment(AppState.self) private var appState
    @State private var conversations: [MWInboxConversation] = []
    @State private var path: [String] = []
    @State private var showCompose = false
    @State private var error: String?
    @State private var loaded = false

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error, loaded {
                    Section { ErrorRow(message: error) { Task { await load() } } }
                }
                if !loaded {
                    ForEach(0..<4, id: \.self) { _ in
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Coworker name").font(.headline)
                            Text("The last message in the conversation").font(.subheadline)
                        }
                        .redacted(reason: .placeholder)
                        .accessibilityLabel("Loading messages")
                    }
                } else {
                    ForEach(conversations) { conversation in
                        NavigationLink(value: conversation.id) {
                            ConversationRow(conversation: conversation, myID: appState.currentUserID ?? "")
                        }
                        .accessibilityIdentifier("conversation.row")
                    }
                }
            }
            .listStyle(.plain)
            .overlay {
                if loaded && conversations.isEmpty && error == nil {
                    ContentUnavailableView {
                        Label("No messages yet", systemImage: "bubble.left.and.bubble.right")
                    } description: {
                        Text("Message a coworker or your manager about a shift.")
                    } actions: {
                        Button("New message") { showCompose = true }
                    }
                }
            }
            .navigationTitle("Messages")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCompose = true } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("New message")
                }
            }
            .navigationDestination(for: String.self) { id in
                DMThreadView(conversationID: id, title: title(for: id))
                    .onDisappear { Task { await load() } }
            }
            .sheet(isPresented: $showCompose) {
                NewConversationView { id in
                    await load()
                    path.append(id)
                }
            }
            .refreshable { await load() }
        }
        .task {
            await load()
            openPendingConversation()
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(20)) }
                catch { break }
                await load()
            }
        }
        .onChange(of: appState.pendingConversationID) { _, _ in openPendingConversation() }
    }

    private func load() async {
        do {
            async let list = InboxService.shared.conversations()
            async let count = InboxService.shared.unreadCount()
            (conversations, appState.unreadMessages) = try await (list, count)
            error = nil
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
        loaded = true
    }

    private func title(for id: String) -> String {
        guard let conversation = conversations.first(where: { $0.id == id }) else { return "Conversation" }
        return DM.title(conversation, myId: appState.currentUserID ?? "")
    }

    private func openPendingConversation() {
        guard let id = appState.pendingConversationID, UUID(uuidString: id) != nil else { return }
        if !path.contains(id) { path.append(id) }
        appState.pendingConversationID = nil
    }
}

private struct ConversationRow: View {
    let conversation: MWInboxConversation
    let myID: String

    private var unread: Int { conversation.unreadCount ?? 0 }

    var body: some View {
        let name = DM.title(conversation, myId: myID)
        HStack(spacing: 12) {
            Avatar(name: name, size: 44)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(name)
                        .font(.headline)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    if let at = conversation.lastMessageAt {
                        Text(Instant.short(at))
                            .font(.caption)
                            .foregroundStyle(Color.secondary)
                    }
                }
                HStack(alignment: .top) {
                    Text(conversation.lastMessagePreview ?? "No messages yet")
                        .font(.subheadline)
                        .foregroundStyle(unread > 0 ? Color.primary : Color.secondary)
                        .lineLimit(2)
                    Spacer(minLength: 8)
                    if unread > 0 {
                        Text("\(min(unread, 99))")
                            .font(.caption.weight(.semibold)).foregroundStyle(.white)
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(Color.accentColor, in: Capsule())
                            .accessibilityLabel("\(unread) unread")
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }
}
