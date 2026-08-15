import SwiftUI

struct NotificationsView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = NotificationsViewModel()

    var body: some View {
        Group {
            if vm.items.isEmpty && !vm.isLoading {
                EmptyState(icon: "bell", title: "No notifications")
            } else {
                List(vm.items) { item in
                    if ["dm_message", "dm_assignment"].contains(item.kind), let threadID = item.reference_id {
                        NavigationLink {
                            DmThreadView(vm: DmThreadViewModel(threadId: threadID))
                        } label: {
                            notificationRow(item)
                        }
                    } else {
                        notificationRow(item)
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Notifications")
        .task {
            await vm.load()
            // Mark-all-read after a brief look, matching the web's behavior.
            try? await Task.sleep(for: .seconds(1))
            await vm.markAllRead()
            appState.unreadCount = 0
        }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }

    private func icon(for kind: String) -> String {
        switch kind {
        case "points_earned", "level_up": return "sparkles"
        case "badge": return "rosette"
        case "redemption": return "ticket"
        case "points_adjustment": return "arrow.up.arrow.down"
        case "feedback": return "bubble.left.and.text.bubble.right"
        case "dm_message", "dm_assignment": return "message"
        case "board_join_request", "membership_approved": return "person.badge.plus"
        case "board_post": return "square.and.pencil"
        case "board_reply_pending", "board_reply_approved": return "bubble.left"
        case "board_team_added": return "person.3"
        default: return "bell"
        }
    }

    private func notificationRow(_ item: TellusNotification) -> some View {
        HStack {
            Image(systemName: icon(for: item.kind))
                .foregroundStyle(item.is_read ? Color.secondary : Color.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.interSubheadline.bold())
                if let body = item.body { Text(body).font(.interCaption).foregroundStyle(.secondary) }
            }
            Spacer()
            Text(Formatters.relativeString(from: item.created_at))
                .font(.interCaption2).foregroundStyle(.secondary)
        }
    }
}
