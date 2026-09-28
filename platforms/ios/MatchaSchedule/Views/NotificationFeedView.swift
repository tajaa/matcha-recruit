import SwiftUI

struct NotificationFeedView: View {
    @Environment(AppState.self) private var appState
    @State private var notifications: [ScheduleNotification] = []
    @State private var error: String?
    @State private var loaded = false
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                if let error { ErrorBanner(message: error) }
                if !loaded {
                    ProgressView().padding(.top, 40)
                } else if notifications.isEmpty && error == nil {
                    GlassMessage(symbol: "bell.badge", title: "You're all caught up",
                                 message: "Schedule updates and replies to your requests land here.")
                        .rise()
                } else {
                    ForEach(Array(notifications.enumerated()), id: \.element.id) { index, notice in
                        Button { Task { await open(notice) } } label: {
                            NoticeRow(notice: notice)
                        }
                        .buttonStyle(PressableStyle())
                        .disabled(busy)
                        .rise(delay: min(Double(index) * 0.03, 0.2))
                    }
                }
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.bottom, 32)
            .animation(.spring(response: 0.4, dampingFraction: 0.86), value: notifications.map(\.is_read))
        }
        .scrollIndicators(.hidden)
        .ambientBackground()
        .navigationTitle("Notifications")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { Task { await markAllRead() } } label: {
                    Text("Mark all read").font(TypeScale.callout)
                }
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

    private var style: (symbol: String, color: Color) {
        switch notice.type {
        case "schedule_published": ("calendar.badge.checkmark", Palette.leaf)
        case "schedule_offer_received": ("arrow.left.arrow.right", Palette.dusk)
        case "schedule_request_accepted": ("hand.thumbsup.fill", Palette.leaf)
        case "schedule_request_withdrawn": ("arrow.uturn.backward", Palette.amber)
        case "schedule_request_decided": ("checkmark.seal.fill", Palette.dusk)
        case "inbox_message": ("bubble.left.fill", Palette.leaf)
        default: ("bell.fill", Palette.inkSoft)
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: style.symbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(style.color)
                .frame(width: 38, height: 38)
                .background(style.color.opacity(0.14), in: Circle())
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(notice.title)
                        .font(.inter(15, notice.is_read ? .semibold : .bold, relativeTo: .headline))
                        .foregroundStyle(Palette.ink)
                    Spacer(minLength: 8)
                    Text(Instant.short(notice.created_at))
                        .font(TypeScale.caption).foregroundStyle(Palette.inkFaint)
                }
                if let body = notice.body {
                    Text(body).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
                        .multilineTextAlignment(.leading)
                }
            }
            if !notice.is_read {
                Circle().fill(Palette.leaf).frame(width: 8, height: 8).padding(.top, 6)
            }
        }
        .padding(14)
        .glassSurface(tint: notice.is_read ? nil : style.color, elevated: !notice.is_read)
        .opacity(notice.is_read ? 0.88 : 1)
    }
}
