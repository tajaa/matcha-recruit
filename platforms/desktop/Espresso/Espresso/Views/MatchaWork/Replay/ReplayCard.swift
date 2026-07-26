import SwiftUI

/// Passive, read-only card for the Weekly Replay board. Mirrors `KanbanCard`'s
/// visual language (avatar, rounded surface, glass edge) but strips every
/// interactive affordance — no checkbox, no move-menu, no drag, no context
/// menu — since it's a frozen historical frame, not a live ticket.
///
/// While `isMoving`, the card wears the look of one held mid-drag: lifted off
/// the board, tilted, and casting a deeper shadow. The board glides it between
/// columns underneath that treatment, so a replayed column change looks like
/// someone dragging the ticket across rather than it blinking to a new slot.
struct ReplayCard: View {
    @Environment(AppState.self) private var appState
    let task: ReplayTaskState
    var isMoving: Bool = false

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
        .scaleEffect(isMoving ? 1.05 : 1.0)
        .rotationEffect(.degrees(isMoving ? -1.5 : 0))
        .shadow(color: .black.opacity(isMoving ? 0.35 : 0), radius: 12, y: 6)
    }
}
