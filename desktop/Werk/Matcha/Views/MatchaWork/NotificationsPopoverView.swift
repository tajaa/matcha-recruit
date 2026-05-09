import SwiftUI

struct NotificationsPopoverView: View {
    @Environment(AppState.self) private var appState
    @State private var notifications: [MWAppNotification] = []
    @State private var loading = true
    @State private var markingAll = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Notifications")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                if !notifications.isEmpty && notifications.contains(where: { !$0.isRead }) {
                    Button {
                        Task { await markAllRead() }
                    } label: {
                        Text(markingAll ? "…" : "Mark all read")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .disabled(markingAll)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)

            Divider().opacity(0.3)

            if loading {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .padding(24)
            } else if notifications.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "bell.slash")
                        .font(.system(size: 22))
                        .foregroundColor(.secondary)
                    Text("No notifications yet")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(24)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(notifications) { n in
                            NotificationRow(notification: n) {
                                Task { await markRead(id: n.id) }
                            }
                            Divider().opacity(0.15)
                        }
                    }
                }
            }
        }
        .frame(width: 340, height: 380)
        .background(Color.appBackground)
        .task { await load() }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        if let rows = try? await MatchaWorkService.shared.fetchNotifications() {
            notifications = rows
        }
        await appState.refreshNotificationsCount()
    }

    private func markRead(id: String) async {
        guard let idx = notifications.firstIndex(where: { $0.id == id }) else { return }
        if notifications[idx].isRead { return }
        notifications[idx] = notifications[idx].markedRead()
        try? await MatchaWorkService.shared.markNotificationsRead(ids: [id])
        await appState.refreshNotificationsCount()
    }

    private func markAllRead() async {
        markingAll = true
        defer { markingAll = false }
        notifications = notifications.map { $0.markedRead() }
        try? await MatchaWorkService.shared.markAllNotificationsRead()
        await appState.refreshNotificationsCount()
    }
}

private extension MWAppNotification {
    func markedRead() -> MWAppNotification {
        MWAppNotification(
            id: id, type: type, title: title, body: body,
            link: link, isRead: true, createdAt: createdAt
        )
    }
}

private struct NotificationRow: View {
    let notification: MWAppNotification
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 10) {
                Circle()
                    .fill(notification.isRead ? Color.clear : Color.matcha500)
                    .frame(width: 7, height: 7)
                    .padding(.top, 5)
                VStack(alignment: .leading, spacing: 3) {
                    Text(notification.title)
                        .font(.system(size: 12, weight: notification.isRead ? .regular : .semibold))
                        .foregroundColor(.white)
                        .multilineTextAlignment(.leading)
                    if let body = notification.body, !body.isEmpty {
                        Text(body)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(3)
                    }
                    Text(formatRelative(notification.createdAt))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .opacity(0.7)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(notification.isRead ? Color.clear : Color.matcha600.opacity(0.06))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func formatRelative(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date: Date? = formatter.date(from: iso) ?? {
            formatter.formatOptions = [.withInternetDateTime]
            return formatter.date(from: iso)
        }()
        guard let d = date else { return iso }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .short
        return rel.localizedString(for: d, relativeTo: Date())
    }
}
