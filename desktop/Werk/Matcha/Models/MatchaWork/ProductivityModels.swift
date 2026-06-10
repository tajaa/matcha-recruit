import Foundation

/// A personal productivity board (kanban). User-scoped — not tied to a project.
struct ProductivityBoard: Codable, Identifiable, Hashable {
    let id: String
    var title: String
    let isDefault: Bool
    let status: String
    let todoCount: Int?
    let inProgressCount: Int?
    let doneCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, status
        case isDefault = "is_default"
        case todoCount = "todo_count"
        case inProgressCount = "in_progress_count"
        case doneCount = "done_count"
    }

    var cardCount: Int { (todoCount ?? 0) + (inProgressCount ?? 0) + (doneCount ?? 0) }
}

/// A card on a personal board. `boardColumn` is one of todo|in_progress|done.
/// May back-link to a journal when created from a text selection.
struct ProductivityCard: Codable, Identifiable, Hashable {
    let id: String
    let boardId: String
    var title: String
    var notes: String?
    var boardColumn: String
    var position: Int
    var dueDate: String?              // "yyyy-MM-dd" — calendar placement; nil = board-only
    let sourceJournalId: String?
    let sourceExcerpt: String?
    let completedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, notes, position
        case boardId = "board_id"
        case boardColumn = "board_column"
        case dueDate = "due_date"
        case sourceJournalId = "source_journal_id"
        case sourceExcerpt = "source_excerpt"
        case completedAt = "completed_at"
    }
}

/// The three personal-board columns, in display order.
enum ProductivityColumn: String, CaseIterable, Identifiable {
    case todo = "todo"
    case inProgress = "in_progress"
    case done = "done"

    var id: String { rawValue }
    var label: String {
        switch self {
        case .todo:       return "To Do"
        case .inProgress: return "In Progress"
        case .done:       return "Done"
        }
    }
    var icon: String {
        switch self {
        case .todo:       return "circle"
        case .inProgress: return "circle.lefthalf.filled"
        case .done:       return "checkmark.circle.fill"
        }
    }
}
