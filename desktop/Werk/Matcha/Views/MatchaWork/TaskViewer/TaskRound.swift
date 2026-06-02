import SwiftUI

/// One round on a kanban ticket — a modular sub-todo housed inside the
/// parent ticket. Rounds chain together explicitly: any collaborator
/// hits "Start Next Round," names the suggested fix, and a new round
/// opens. Round 1 covers the initial work from creation up to the first
/// `round_started` event; each subsequent `round_started` row in
/// mw_task_history opens a new round and lands at the TOP of it.
///
/// Events inside a round stay chronological so the round reads as a
/// self-contained story: "round opened (suggested fix: X) · subtask
/// added · note · ... · next round_started → this round closes."
struct TaskRound: Identifiable {
    let index: Int
    let events: [MWTaskHistoryEntry]
    let isLatest: Bool

    var id: Int { index }

    /// Round title — for round N>=2, the `suggested_fix_title` from the
    /// opening `round_started` event. For round 1, falls back to a
    /// generic label so the UI always has something to render.
    var title: String {
        if let opener = events.first, opener.eventType == "round_started",
           let t = (opener.metadata?["title"])?.trimmingCharacters(in: .whitespacesAndNewlines),
           !t.isEmpty {
            return t
        }
        return "Initial work"
    }

    /// True when this round was opened by an explicit `round_started`
    /// event (vs the implicit round 1 that starts at task creation).
    var hasExplicitOpener: Bool {
        events.first?.eventType == "round_started"
    }

    /// Subtask titles completed during this round. Drives the "Fixed in
    /// Round N-1" inheritance block at the top of the NEXT round so the
    /// reviewer sees what got addressed at a glance.
    var fixedSubtaskTitles: [String] {
        events
            .filter { $0.eventType == "subtask_completed" }
            .compactMap { ($0.metadata?["title"])?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    /// Highest-signal column the round currently sits in, used in the round
    /// header chip ("Round 3 · In Review", "Round 2 · Sent back"). Derived
    /// from the last column_change in this round; defaults to "Active" /
    /// "Closed" based on whether this is the latest round.
    func phaseLabel(isLatest: Bool) -> String {
        if let last = events.reversed().first(where: { $0.eventType == "column_change" }),
           let col = last.toValue {
            switch col {
            case "todo": return "Todo"
            case "in_progress": return "In Progress"
            case "review": return "In Review"
            case "changes_requested": return "Sent Back"
            case "done": return "Done"
            default: return col.replacingOccurrences(of: "_", with: " ").capitalized
            }
        }
        return isLatest ? "Active" : "Closed"
    }

    func phaseColor(isLatest: Bool) -> Color {
        if let last = events.reversed().first(where: { $0.eventType == "column_change" }) {
            switch last.toValue ?? "" {
            case "review": return .blue
            case "changes_requested": return .orange
            case "done": return .matcha500
            case "in_progress": return .yellow
            default: break
            }
        }
        return isLatest ? .matcha500 : .secondary
    }

    /// Build rounds from a flat history list. Round boundaries are EXPLICIT
    /// — only `round_started` events open new rounds. Column moves are
    /// informational events that live inside whatever round they fall in,
    /// no longer triggering boundaries on their own.
    static func build(from history: [MWTaskHistoryEntry]) -> [TaskRound] {
        let sorted = history.sorted { $0.createdAt < $1.createdAt }
        var buckets: [[MWTaskHistoryEntry]] = [[]]
        for e in sorted {
            if e.eventType == "round_started" {
                // Open a new round; the round_started event itself goes at
                // the top of the new round so the title + subtask hook
                // render first.
                buckets.append([])
            }
            buckets[buckets.count - 1].append(e)
        }
        if buckets.last?.isEmpty == true { buckets.removeLast() }
        if buckets.isEmpty { return [] }
        return buckets.enumerated().map { idx, events in
            TaskRound(index: idx + 1, events: events, isLatest: idx == buckets.count - 1)
        }
    }
}
