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
                Section { ErrorRow(message: error) { Task { await load() } } }
            }
            if !loaded {
                Section { HStack { ProgressView(); Text("Loading notifications").foregroundStyle(Color.secondary) } }
            } else if !notifications.isEmpty {
                ForEach(notifications) { notice in
                    Button { Task { await open(notice) } } label: {
                        NoticeRow(notice: notice)
                    }
                    .disabled(busy)
                }
            }
        }
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
            notifications = try await NotificationService.list().notifications
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
        case "inbox_message": "bubble.left"
        default: "bell"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .foregroundStyle(notice.is_read ? Color.secondary : Color.accentColor)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(notice.title)
                        .font(notice.is_read ? .body : .headline)
                        .foregroundStyle(Color.primary)
                    Spacer(minLength: 8)
                    Text(Instant.short(notice.created_at))
                        .font(.caption).foregroundStyle(Color.secondary)
                }
                if let body = notice.body {
                    Text(body).font(.subheadline).foregroundStyle(Color.secondary)
                        .multilineTextAlignment(.leading)
                }
            }
            if !notice.is_read {
                Circle().fill(Color.accentColor).frame(width: 8, height: 8).padding(.top, 6)
                    .accessibilityLabel("Unread")
            }
        }
    }
}
