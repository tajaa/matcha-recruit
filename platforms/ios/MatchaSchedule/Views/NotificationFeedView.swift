import SwiftUI

struct NotificationFeedView: View {
    @Environment(AppState.self) private var appState
    @State private var notifications: [ScheduleNotification] = []
    @State private var error: String?
    @State private var loaded = false
    @State private var busy = false

    var body: some View {
        List {
            if !loaded { ProgressView("Loading notifications…") }
            if notifications.isEmpty && loaded && error == nil {
                ContentUnavailableView("All caught up", systemImage: "bell")
            }
            if let error { Text(error).foregroundStyle(.red) }
            ForEach(notifications) { notice in
                Button { Task { await open(notice) } } label: {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: notice.is_read ? "bell" : "bell.badge.fill")
                            .foregroundStyle(notice.is_read ? Color.secondary : Color.brown)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(notice.title).font(.headline)
                            if let body = notice.body { Text(body).font(.subheadline) }
                            Text(notice.created_at.prefix(10))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 0)
                    }
                    .foregroundStyle(.primary)
                    .padding(.vertical, 5)
                }
                .disabled(busy)
            }
        }
        .navigationTitle("Notifications")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Mark all read") { Task { await markAllRead() } }
                    .disabled(busy || appState.unreadNotifications == 0)
            }
        }
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do {
            notifications = try await NotificationService.list().notifications
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
        await appState.refreshBadges()
    }

    private func open(_ notice: ScheduleNotification) async {
        busy = true
        defer { busy = false }
        do {
            if !notice.is_read { try await NotificationService.markRead([notice.id]) }
            await load()
            var payload: [AnyHashable: Any] = ["type": notice.type]
            if let link = notice.link { payload["link"] = link }
            if let id = notice.metadata?.conversation_id {
                payload["metadata"] = ["conversation_id": id]
            }
            appState.handlePush(payload)
        } catch { self.error = error.localizedDescription }
    }

    private func markAllRead() async {
        busy = true
        defer { busy = false }
        do {
            try await NotificationService.markAllRead()
            await load()
        } catch { self.error = error.localizedDescription }
    }
}
