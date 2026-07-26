import Foundation

// MARK: - Board column vocabulary
//
// Split out of KanbanBoardView.swift. These are module-wide (KanbanCard,
// KanbanListView, ReplayBoardView, TaskEditor, AIDraftReview and
// ProjectDetailViewModel all read them), so they belong beside the board
// rather than inside the file of one of its views.

let kanbanColumns: [(key: String, label: String)] = [
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("changes_requested", "Changes Requested"),
    ("done", "Done"),
]

/// Board vs sales-pipeline column set. Internal (was file-private) so the
/// board's own split-out column/toolbar extensions can name it.
enum KanbanViewMode { case board, pipeline }

func columnsFor(mode: KanbanViewMode) -> [(key: String, label: String)] {
    mode == .pipeline ? SalesStage.columns : kanbanColumns
}

func columnsFor(pipeline: Bool) -> [(key: String, label: String)] {
    columnsFor(mode: pipeline ? .pipeline : .board)
}

/// Compact currency for deal values / pipeline totals — "$12k", "$1.2M",
/// "$0" when nil/zero. Pipeline-mode only.
func formatDealValue(_ value: Double) -> String {
    let v = value
    if v >= 1_000_000 { return String(format: "$%.1fM", v / 1_000_000) }
    if v >= 1_000 { return String(format: "$%.0fk", v / 1_000) }
    return String(format: "$%.0f", v)
}
