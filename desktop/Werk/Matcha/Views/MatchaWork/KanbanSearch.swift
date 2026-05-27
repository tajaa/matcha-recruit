import Foundation

/// Kanban board search tokenizing + matching. Extracted from KanbanBoardView so
/// both the view's search field and ProjectDetailViewModel's grouped-column
/// cache use one implementation (the cache filters tasks before sorting, so the
/// match logic can't live as a private view method).
enum KanbanSearch {
    /// Splits a query into tokens. Quoted substrings (e.g. `"login page"`) are
    /// treated as a single phrase token; unquoted space-separated words are
    /// individual AND terms.
    static func tokens(_ query: String) -> [String] {
        var tokens: [String] = []
        var current = ""
        var inQuotes = false
        for ch in query {
            switch ch {
            case "\"":
                if inQuotes {
                    if !current.isEmpty { tokens.append(current); current = "" }
                    inQuotes = false
                } else {
                    inQuotes = true
                }
            case " " where !inQuotes:
                if !current.isEmpty { tokens.append(current); current = "" }
            default:
                current.append(ch)
            }
        }
        if !current.isEmpty { tokens.append(current) }
        return tokens.filter { !$0.isEmpty }
    }

    /// True when every token (AND semantics) appears in the task's searchable
    /// fields. An empty `tokens` array matches everything.
    static func matches(_ task: MWProjectTask, tokens: [String]) -> Bool {
        guard !tokens.isEmpty else { return true }
        let haystack = [
            task.title,
            task.description ?? "",
            task.progressNote ?? "",
            task.displayAssignee ?? "",
            task.priority,
            task.category ?? "",
            task.boardColumn,
        ].joined(separator: " ").lowercased()
        return tokens.allSatisfy { haystack.contains($0.lowercased()) }
    }
}
