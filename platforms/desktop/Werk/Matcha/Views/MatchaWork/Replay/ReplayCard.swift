import SwiftUI

/// Passive, read-only card for the Weekly Replay board. Mirrors `KanbanCard`'s
/// visual language (avatar, rounded surface, glass edge) but strips every
/// interactive affordance — no checkbox, no move-menu, no drag, no context
/// menu — since it's a frozen historical frame, not a live ticket.
struct ReplayCard: View {
    @Environment(AppState.self) private var appState
    let task: ReplayTaskState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(task.title)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(appState.themeText)
                .lineLimit(3)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)

            if let name = task.assigneeName {
                HStack(spacing: 5) {
                    ChannelAvatarView(
                        senderId: task.id,
                        payloadURL: task.assigneeAvatarUrl,
                        name: name,
                        size: 15
                    )
                    Text(name)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .elevatedCard(cornerRadius: 10)
    }
}
