import SwiftUI

/// Direct-message conversation list.
struct InboxListView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = InboxListViewModel()
    @State private var showCompose = false
    @State private var path: [String] = []

    private var myId: String { appState.currentUser?.id ?? "" }

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if vm.isLoading && vm.conversations.isEmpty {
                    ProgressView()
                } else if vm.conversations.isEmpty {
                    ContentUnavailableView(
                        "No messages",
                        systemImage: "bubble.left.and.bubble.right",
                        description: Text(vm.errorMessage ?? "Start a conversation with the pencil button.")
                    )
                } else {
                    List(vm.conversations) { conv in
                        NavigationLink(value: conv.id) {
                            DMConversationRow(conversation: conv, myId: myId)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Messages")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCompose = true } label: {
                        Image(systemName: "square.and.pencil")
                    }
                }
            }
            .navigationDestination(for: String.self) { cid in
                DMThreadView(conversationId: cid, titleHint: titleForId(cid))
                    .onAppear { vm.markConversationRead(cid) }
            }
            .sheet(isPresented: $showCompose) {
                NewConversationView { await vm.load() }
            }
            .refreshable { await vm.load() }
        }
        .task { await vm.load(initial: true) }
        .onChange(of: appState.pendingConversationId) { _, id in
            guard let id else { return }
            if !path.contains(id) { path.append(id) }
            appState.pendingConversationId = nil
        }
        .badge(vm.unreadTotal)
    }

    private func titleForId(_ cid: String) -> String {
        guard let conv = vm.conversations.first(where: { $0.id == cid }) else { return "Conversation" }
        return DM.title(conv, myId: myId)
    }
}

private struct DMConversationRow: View {
    let conversation: MWInboxConversation
    let myId: String

    var body: some View {
        let info = DM.avatar(conversation, myId: myId)
        HStack(spacing: 12) {
            Avatar(url: info.url, name: info.name, size: 46)
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(DM.title(conversation, myId: myId))
                        .font(.body.weight(.semibold))
                        .lineLimit(1)
                    Spacer()
                    Text(ChatTime.shortRelative(conversation.lastMessageAt))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                HStack {
                    Text(conversation.lastMessagePreview ?? "No messages yet")
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    Spacer()
                    if let unread = conversation.unreadCount, unread > 0 {
                        Text("\(min(unread, 99))")
                            .font(.caption2.bold()).foregroundStyle(.white)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(.tint, in: Capsule())
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
