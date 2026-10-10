import SwiftUI

struct NotificationFeedView: View {
    @Environment(AppState.self) private var appState
    @State private var notifications: [ScheduleNotification] = []
    @State private var error: String?
    @State private var loaded = false
    @State private var busy = false

    var body: some View {
        List {
            if let error {
                ErrorRow(message: error) { Task { await load() } }.cardRow()
            }
            if !loaded {
                HStack { ProgressView(); Text("Loading notifications").foregroundStyle(Color.secondary) }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardRow()
            } else {
                ForEach(notifications) { notice in
                    Button { Task { await open(notice) } } label: {
                        NoticeRow(notice: notice)
                    }
                    .disabled(busy)
                    .cardRow()
                }
            }
        }
        .listStyle(.plain)
        .appBackdrop()
        .overlay {
            if loaded && notifications.isEmpty && error == nil {
                ContentUnavailableView("You're all caught up", systemImage: "bell",
                                       description: Text("Schedule updates and replies to your requests land here."))
            }
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
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
            notifications = try await NotificationService.list(typePrefix: appState.notificationPrefix).notifications
            error = nil
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
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
            var metadata: [String: Any] = [:]
            if let id = notice.metadata?.conversation_id { metadata["conversation_id"] = id }
            if let id = notice.metadata?.request_id { metadata["request_id"] = id }
            if !metadata.isEmpty { payload["metadata"] = metadata }
            appState.handlePush(payload)
        } catch { self.error = error.localizedDescription }
    }

    private func markAllRead() async {
        busy = true
        defer { busy = false }
        do {
            if appState.notificationPrefix == nil {
                try await NotificationService.markAllRead()
            } else {
                // Only what this screen shows: "all" would also clear a
                // business admin's web notifications.
                try await NotificationService.markRead(notifications.filter { !$0.is_read }.map(\.id))
            }
            await load()
        } catch { self.error = error.localizedDescription }
    }
}

private struct NoticeRow: View {
    let notice: ScheduleNotification

    private var symbol: String {
        switch notice.type {
        case "schedule_published": "calendar.badge.checkmark"
        case "schedule_break_reminder": "cup.and.saucer"
        case "schedule_offer_received": "arrow.left.arrow.right"
        case "schedule_request_accepted": "hand.thumbsup"
        case "schedule_request_withdrawn": "arrow.uturn.backward"
        case "schedule_request_decided": "checkmark.seal"
        case "schedule_request_pending": "tray.full"
        case "inbox_message": "bubble.left"
        default: "bell"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .foregroundStyle(notice.is_read ? Color.secondary : Color.brand)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(notice.title)
                        .font(notice.is_read ? .body : .headline)
                        .foregroundStyle(Color.primary)
                    Spacer(minLength: 8)
                    Text(Instant.short(notice.created_at))
                        .font(.app(.caption)).foregroundStyle(Color.secondary)
                }
                if let body = notice.body {
                    Text(body).font(.app(.subheadline)).foregroundStyle(Color.secondary)
                        .multilineTextAlignment(.leading)
                }
            }
            if !notice.is_read {
                Circle().fill(Color.brand).frame(width: 8, height: 8).padding(.top, 6)
                    .accessibilityLabel("Unread")
            }
        }
    }
}
