import SwiftUI

/// Authenticated root: the list of channels the user belongs to, with unread
/// badges and push-navigation into each channel's chat.
struct ChannelListView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = ChannelListViewModel()
    @State private var path: [ChannelSummary] = []

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if vm.isLoading && vm.channels.isEmpty {
                    ProgressView()
                } else if vm.channels.isEmpty {
                    ContentUnavailableView(
                        "No channels",
                        systemImage: "bubble.left.and.bubble.right",
                        description: Text(vm.errorMessage ?? "You're not in any channels yet.")
                    )
                } else {
                    List(vm.channels) { channel in
                        NavigationLink(value: channel) {
                            ChannelRow(channel: channel)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Channels")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { accountMenu }
            }
            .navigationDestination(for: ChannelSummary.self) { channel in
                ChannelChatView(channel: channel)
                    .onAppear { vm.clearUnread(channelId: channel.id) }
            }
            .refreshable { await vm.load() }
        }
        .task { await vm.load(initial: true) }
        .onAppear { wireGlobalMessages() }
        .onChange(of: appState.pendingChannelId) { _, id in
            guard let id, let channel = vm.channels.first(where: { $0.id == id }) else { return }
            path = [channel]
            appState.pendingChannelId = nil
        }
    }

    private var accountMenu: some View {
        Menu {
            if let user = appState.currentUser {
                Text(user.name ?? user.email)
                if user.name != nil { Text(user.email) }
            }
            Divider()
            Button("Log Out", role: .destructive) { appState.logout() }
        } label: {
            Avatar(
                url: appState.currentUser?.avatarUrl,
                name: appState.currentUser?.name ?? appState.currentUser?.email ?? "?",
                size: 30
            )
        }
    }

    /// Bump unread on the list when a message lands for a channel we're not
    /// currently viewing. (Phase 5 moves this fan-out into AppState alongside
    /// the APNs path.)
    private func wireGlobalMessages() {
        ChannelsWebSocket.shared.onMessageGlobal = { msg in
            Task { @MainActor in
                guard msg.senderId != appState.currentUser?.id,
                      appState.selectedChannelId != msg.channelId else { return }
                vm.bumpUnread(channelId: msg.channelId, preview: msg.content, at: msg.createdAt)
            }
        }
    }
}

private struct ChannelRow: View {
    let channel: ChannelSummary

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(.secondarySystemBackground))
                    .frame(width: 44, height: 44)
                Image(systemName: channel.isPaid ? "lock.fill" : "number")
                    .foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(channel.name)
                        .font(.body.weight(.semibold))
                        .lineLimit(1)
                    Spacer()
                    Text(ChatTime.shortRelative(channel.lastMessageAt))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                HStack {
                    Text(channel.lastMessagePreview ?? channel.description ?? "No messages yet")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Spacer()
                    if channel.unreadCount > 0 {
                        Text("\(min(channel.unreadCount, 99))")
                            .font(.caption2.bold())
                            .foregroundStyle(.white)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(.tint, in: Capsule())
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
