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
            ScrollView {
                VStack(spacing: 10) {
                    if let error, loaded { ErrorBanner(message: error) }
                    if !loaded {
                        ForEach(0..<4, id: \.self) { _ in ConversationPlaceholder() }
                    } else if conversations.isEmpty {
                        GlassMessage(
                            symbol: "bubble.left.and.bubble.right.fill",
                            title: "No messages yet",
                            message: "Message a coworker or your manager about a shift.",
                            actionTitle: "New message",
                            action: { showCompose = true }
                        )
                        .rise()
                    } else {
                        ForEach(Array(conversations.enumerated()), id: \.element.id) { index, conversation in
                            NavigationLink(value: conversation.id) {
                                ConversationRow(conversation: conversation, myID: appState.currentUserID ?? "")
                            }
                            .buttonStyle(PressableStyle())
                            .accessibilityIdentifier("conversation.row")
                            .rise(delay: min(Double(index) * 0.03, 0.2))
                        }
                    }
                }
                .padding(.horizontal, Metrics.gutter)
                .padding(.bottom, 32)
                .animation(.spring(response: 0.45, dampingFraction: 0.86), value: conversations.map(\.id))
            }
            .scrollIndicators(.hidden)
            .ambientBackground()
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
                .presentationCornerRadius(32)
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
        HStack(spacing: 14) {
            ZStack(alignment: .topTrailing) {
                Avatar(name: name, size: 50)
                if unread > 0 {
                    Circle().fill(Palette.leaf)
                        .frame(width: 13, height: 13)
                        .overlay(Circle().strokeBorder(Palette.surfaceSolid, lineWidth: 2))
                        .offset(x: 2, y: -2)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(name)
                        .font(.inter(16, unread > 0 ? .bold : .semibold, relativeTo: .headline))
                        .foregroundStyle(Palette.ink)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    if let at = conversation.lastMessageAt {
                        Text(Instant.short(at))
                            .font(TypeScale.caption)
                            .foregroundStyle(unread > 0 ? Palette.leaf : Palette.inkFaint)
                    }
                }
                HStack(alignment: .top) {
                    Text(conversation.lastMessagePreview ?? "No messages yet")
                        .font(unread > 0 ? .inter(14, .medium, relativeTo: .subheadline) : TypeScale.subhead)
                        .foregroundStyle(unread > 0 ? Palette.ink : Palette.inkSoft)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    Spacer(minLength: 8)
                    if unread > 0 {
                        Text("\(min(unread, 99))")
                            .font(TypeScale.caption).foregroundStyle(.white)
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(Palette.leaf, in: Capsule())
                    }
                }
            }
        }
        .padding(14)
        .glassSurface(elevated: unread > 0)
        .contentShape(Rectangle())
    }
}

private struct ConversationPlaceholder: View {
    var body: some View {
        HStack(spacing: 14) {
            Circle().fill(Palette.inkFaint.opacity(0.2)).frame(width: 50, height: 50)
            VStack(alignment: .leading, spacing: 8) {
                RoundedRectangle(cornerRadius: 5).fill(Palette.inkFaint.opacity(0.22)).frame(width: 130, height: 13)
                RoundedRectangle(cornerRadius: 5).fill(Palette.inkFaint.opacity(0.15)).frame(width: 200, height: 11)
            }
            Spacer()
        }
        .padding(14)
        .glassSurface(elevated: false)
        .accessibilityLabel("Loading messages")
    }
}
