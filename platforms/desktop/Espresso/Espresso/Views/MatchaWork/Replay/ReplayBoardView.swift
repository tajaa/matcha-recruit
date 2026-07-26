import SwiftUI

/// Passive, read-only kanban board for the Weekly Replay tab. Reuses the same
/// `kanbanColumns` layout as the live board (`KanbanBoardView.swift`) and the
/// exact card-glide technique (`matchedGeometryEffect` + a shared namespace)
/// already proven there for animating a card between columns — but drives it
/// from a frozen `[ReplayTaskState]` snapshot instead of live WS-synced tasks.
///
/// Three things the glide depends on, each easy to break:
///   1. `tasks` arrives in a stable order (see `WeeklyReplayViewModel.orderedTasks`).
///      A reshuffled array makes every card look like it moved.
///   2. The `.animation` lives on the HStack that owns ALL columns. On a single
///      column instead, the insert into the destination animates from that
///      column's own prior geometry and the card teleports.
///   3. Cards take `.transition(.identity)`. A move is a removal from one
///      column plus an insert into another; any fade/scale transition
///      cross-dissolves those two copies (leaving a ghost fading at the origin)
///      instead of letting the single card glide. The transition can't be made
///      conditional on "is this card moving" either — the removed view carries
///      the transition it was built with a frame earlier, before the move was
///      known. Cost of `.identity`: created and deleted cards pop rather than
///      fade. Worth it; the glide is the point of the tab.
struct ReplayBoardView: View {
    @Environment(AppState.self) private var appState
    let tasks: [ReplayTaskState]
    /// The card mid-move, lifted like a dragged ticket. Nil when nothing moved.
    let movingTaskId: String?
    @Namespace private var cardNS

    /// Matches `WeeklyReplayViewModel.liftDuration` — the lift drops as the
    /// card lands, so pick-up, glide, and drop are one continuous gesture.
    private let glide = Animation.spring(response: 0.45, dampingFraction: 0.82)

    private func tasksFor(column: String) -> [ReplayTaskState] {
        tasks.filter { $0.column == column && !$0.isDeleted }
    }

    var body: some View {
        // One scroll view around the whole board, not one per column: a card
        // gliding from "todo" to "done" has to render outside its column's
        // bounds, and a per-column ScrollView clips it away mid-flight.
        ScrollView([.horizontal, .vertical]) {
            HStack(alignment: .top, spacing: 12) {
                ForEach(kanbanColumns, id: \.key) { col in
                    columnView(key: col.key, label: col.label)
                        // Draw the column holding the moving card above its
                        // neighbours, so a card travelling left doesn't slide
                        // underneath the columns it passes.
                        .zIndex(tasksFor(column: col.key).contains { $0.id == movingTaskId } ? 1 : 0)
                }
            }
            .padding(12)
            .animation(glide, value: tasks)
            .animation(glide, value: movingTaskId)
        }
    }

    private func columnView(key: String, label: String) -> some View {
        let items = tasksFor(column: key)
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(label.uppercased())
                    .font(.system(size: 11, weight: .bold))
                    .tracking(0.5)
                    .foregroundColor(.secondary)
                Text("\(items.count)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(appState.themeText.opacity(0.08))
                    .cornerRadius(6)
                Spacer()
            }
            .padding(.horizontal, 4)

            // Plain VStack, not LazyVStack: matchedGeometryEffect needs both
            // the source and destination card realized in the same frame, and
            // a lazy stack hasn't built the off-screen one yet. A week's board
            // is dozens of cards, so eager layout costs nothing.
            VStack(spacing: 8) {
                ForEach(items) { task in
                    let isMoving = task.id == movingTaskId
                    ReplayCard(task: task, isMoving: isMoving)
                        .matchedGeometryEffect(id: task.id, in: cardNS)
                        .zIndex(isMoving ? 1 : 0)
                        .transition(.identity)
                }
            }
        }
        .frame(width: 240, alignment: .top)
    }
}
