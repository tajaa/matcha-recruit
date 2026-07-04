import SwiftUI

/// Passive, read-only kanban board for the Weekly Replay tab. Reuses the same
/// `kanbanColumns` layout as the live board (`KanbanBoardView.swift`) and the
/// exact card-glide technique (`matchedGeometryEffect` + a shared namespace)
/// already proven there for animating a card between columns — but drives it
/// from a frozen `[ReplayTaskState]` snapshot instead of live WS-synced tasks.
/// Deleted cards fade out via ForEach's natural removal transition rather than
/// an internal opacity toggle, so they don't also trigger the move-glide.
struct ReplayBoardView: View {
    @Environment(AppState.self) private var appState
    let tasks: [ReplayTaskState]
    @Namespace private var cardNS

    private func tasksFor(column: String) -> [ReplayTaskState] {
        tasks.filter { $0.column == column && !$0.isDeleted }
    }

    var body: some View {
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 12) {
                ForEach(kanbanColumns, id: \.key) { col in
                    columnView(key: col.key, label: col.label)
                }
            }
            .padding(12)
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

            ScrollView(.vertical) {
                LazyVStack(spacing: 8) {
                    ForEach(items) { task in
                        ReplayCard(task: task)
                            .matchedGeometryEffect(id: task.id, in: cardNS)
                            .transition(.opacity.combined(with: .scale(scale: 0.92)))
                    }
                }
            }
        }
        .frame(width: 240, alignment: .top)
        .animation(.spring(response: 0.4, dampingFraction: 0.8), value: tasks)
    }
}
