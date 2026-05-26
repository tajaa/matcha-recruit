import SwiftUI

// Leaf views split out of ContentView so that frequently-churning AppState
// fields (notificationsUnreadCount, unreadInboxCount — both ticked on every
// inbound WS notification and on the 60s polls) re-render only a small badge
// instead of the whole ContentView body. ContentView.body inlines every
// @ViewBuilder computed prop + the .toolbar closure into one @Observable
// tracking scope, so a count read there rebuilds BOTH split panes (each a full
// chat tree) mid-scroll/type. Reading the counts down here keeps the panes out
// of that scope. See plan: side-by-side split scroll/type jank.

// MARK: - Detail panes

/// Primary (left) detail pane. Reads only the selection-routing fields, which
/// change on user navigation — never on a WS/poll tick — so the heavy detail
/// tree no longer rebuilds when an unread counter increments.
struct PrimaryDetailPane: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if let threadId = appState.selectedThreadId {
                ThreadDetailView(threadId: threadId)
                    .onChange(of: threadId) { appState.showSkills = false }
            } else if let projectId = appState.selectedProjectId {
                ProjectDetailView(projectId: projectId)
            } else if let journalId = appState.selectedJournalId {
                JournalDetailView(journalId: journalId)
            } else if let channelId = appState.selectedChannelId {
                ChannelDetailView(channelId: channelId)
            } else if appState.showChannelBrowse {
                ChannelBrowseView()
            } else if appState.showInbox {
                InboxView()
            } else if appState.showPeople {
                PeopleView()
            } else if appState.showSkills {
                SkillsView()
            } else if appState.showArchive {
                ArchiveView()
            } else {
                HomeDashboardView()
            }
        }
    }
}

/// Secondary (right) split pane — pinned to `target`. Renders via
/// AuxWindowRootView (isEmbedded, so it never writes shared nav state). Reads
/// only theme + the value-typed `target`, so WS/poll churn can't rebuild it.
struct SplitSecondaryPane: View {
    let target: AuxWindowTarget
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "rectangle.split.2x1")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                Text(label)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button {
                    openWindow(id: "aux", value: target)
                    appState.splitTarget = nil
                } label: {
                    Image(systemName: "macwindow.on.rectangle")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Pop out to a window")
                Button { appState.splitTarget = nil } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Close split")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            Divider().opacity(0.2)
            AuxWindowRootView(target: target)
        }
    }

    private var label: String {
        switch target {
        case .project: return "Project"
        case .channel: return "Channel"
        case .thread: return "Thread"
        case .journal: return "Journal"
        }
    }
}

// MARK: - Churning-counter leaf badges

/// Toolbar bell label. Reads `notificationsUnreadCount` here so its ticks
/// re-render only this badge, not ContentView. The Button + popover stay in
/// ContentView (they own the `showNotifications` @State).
struct NotificationBellBadge: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Image(systemName: "bell")
                .font(.system(size: 13))
                .foregroundColor(appState.themeText.opacity(0.7))
            if appState.notificationsUnreadCount > 0 {
                Text(appState.notificationsUnreadCount > 9 ? "9+" : "\(appState.notificationsUnreadCount)")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 3)
                    .padding(.vertical, 1)
                    .background(Color.red)
                    .clipShape(Capsule())
                    .offset(x: 6, y: -5)
            }
        }
        .frame(width: 22, height: 16)
    }
}

/// Reusable sidebar footer button. Theme reads only (non-churning).
struct SidebarFooterButton: View {
    let icon: String
    let label: String
    var badge: Int = 0
    let isActive: Bool
    let action: () -> Void
    @Environment(AppState.self) private var appState

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(isActive ? appState.themeAccent : appState.themeTextSecondary)
                Text(label)
                    .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                    .foregroundColor(isActive ? appState.themeAccent : appState.themeText.opacity(0.85))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                if badge > 0 {
                    Text("\(badge)")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeAccent)
                        .clipShape(Capsule())
                }
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive ? appState.themeAccent.opacity(0.14) : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }
}

/// Inbox footer button. Reads `unreadInboxCount` (and `showInbox`) here so its
/// ticks re-render only this button, not ContentView. `action` is supplied by
/// ContentView (it mutates the shared nav flags).
struct InboxFooterButton: View {
    let action: () -> Void
    @Environment(AppState.self) private var appState

    var body: some View {
        SidebarFooterButton(
            icon: "envelope",
            label: "Inbox",
            badge: appState.unreadInboxCount,
            isActive: appState.showInbox,
            action: action
        )
    }
}
