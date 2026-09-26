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
            Group {
                if !loaded {
                    ProgressView("Loading messages…")
                } else if conversations.isEmpty {
                    ContentUnavailableView(
                        "No messages", systemImage: "bubble.left.and.bubble.right",
                        description: Text(error ?? "Start a conversation with the compose button.")
                    )
                } else {
                    List(conversations) { conversation in
                        NavigationLink(value: conversation.id) {
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text(DM.title(conversation, myId: appState.currentUserID ?? ""))
                                        .font(.headline).lineLimit(1)
                                    Spacer()
                                    if let unread = conversation.unreadCount, unread > 0 {
                                        Text("\(min(unread, 99))")
                                            .font(.caption2.bold()).foregroundStyle(.white)
                                            .padding(.horizontal, 7).padding(.vertical, 3)
                                            .background(.tint, in: Capsule())
                                    }
                                }
                                Text(conversation.lastMessagePreview ?? "No messages yet")
                                    .font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                    .listStyle(.plain)
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
        } catch { self.error = error.localizedDescription }
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
