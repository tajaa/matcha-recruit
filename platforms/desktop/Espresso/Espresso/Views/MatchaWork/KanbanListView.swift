/// KanbanListView — linear alternative to the kanban board. Same tickets,
/// same memoized grouping (zero extra per-frame work), rendered as flat rows
/// grouped under column section headers, with a "Mine" filter for tasks
/// assigned to the current user. Tapping a row opens the same read-only
/// TaskViewerSheet the board cards use (via `onOpen`).

import SwiftUI

struct KanbanListView: View {
    @Environment(AppState.self) private var appState
    @Bindable var viewModel: ProjectDetailViewModel
    let isPipeline: Bool
    let searchText: String
    let myUserId: String
    let onOpen: (MWProjectTask) -> Void

    /// Persisted so the filter survives board re-mounts within a session.
    @AppStorage("mw-kanban-list-mine") private var mineOnly = false

    private var grouped: [String: [MWProjectTask]] {
        viewModel.groupedColumns(pipeline: isPipeline, search: searchText)
    }

    private func rows(for key: String) -> [MWProjectTask] {
        let all = grouped[key] ?? []
        guard mineOnly else { return all }
        return all.filter { $0.assignedTo == myUserId }
    }

    private var totalShown: Int {
        columnsFor(pipeline: isPipeline).reduce(0) { $0 + rows(for: $1.key).count }
    }

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            ScrollView(.vertical, showsIndicators: false) {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(columnsFor(pipeline: isPipeline), id: \.key) { col in
                        let tasks = rows(for: col.key)
                        if !tasks.isEmpty {
                            sectionHeader(label: col.label, count: tasks.count)
                            ForEach(tasks) { task in
                                listRow(task)
                                Divider().opacity(0.08)
                            }
                        }
                    }
                    if totalShown == 0 {
                        Text(mineOnly ? "Nothing assigned to you here." : "No tickets yet.")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 28)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.bottom, 12)
            }
        }
    }

    // MARK: - Filter bar

    private var filterBar: some View {
        HStack(spacing: 6) {
            filterButton("All", active: !mineOnly) { mineOnly = false }
            filterButton("Mine", active: mineOnly) { mineOnly = true }
            Spacer()
            Text("\(totalShown) ticket\(totalShown == 1 ? "" : "s")")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func filterButton(_ label: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .padding(.horizontal, 9)
                .padding(.vertical, 3)
                .background(active ? appState.themeAccent.opacity(0.15) : Color.clear)
                .foregroundColor(active ? appState.themeAccent : .secondary)
                .cornerRadius(5)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Rows

    private func sectionHeader(label: String, count: Int) -> some View {
        HStack(spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.5)
                .foregroundColor(.secondary)
            Text("\(count)")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(.secondary)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .background(appState.themeText.opacity(0.07))
                .cornerRadius(6)
            Spacer()
        }
        .padding(.horizontal, 4)
        .padding(.top, 14)
        .padding(.bottom, 5)
    }

    private func priorityColor(_ priority: String) -> Color {
        switch priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        case "low": return .gray
        default: return .gray.opacity(0.5)
        }
    }

    private func listRow(_ task: MWProjectTask) -> some View {
        let hasUpdates = TicketUpdatesStore.shared.unviewedCount(task) > 0
        return Button {
            onOpen(task)
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(priorityColor(task.priority))
                    .frame(width: 7, height: 7)
                Text(task.title)
                    .font(.system(size: 12, weight: hasUpdates ? .semibold : .regular))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                if hasUpdates {
                    Circle().fill(Color.yellow).frame(width: 5, height: 5)
                }
                if let cat = task.category, !cat.isEmpty {
                    Text(cat)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeText.opacity(0.06))
                        .cornerRadius(4)
                }
                Spacer()
                if let total = task.subtaskTotal, total > 0 {
                    Text("\(task.subtaskDone ?? 0)/\(total)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.secondary)
                }
                if let name = task.displayAssignee {
                    Text(name)
                        .font(.system(size: 10))
                        .foregroundColor(task.assignedTo == myUserId ? appState.themeAccent : .secondary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 7)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
