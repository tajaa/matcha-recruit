import Foundation

// MARK: - Board "replay changes" model
//
// Split out of KanbanBoardView.swift. When the board opens it briefly shows
// each ticket where it was the LAST time THIS user looked, then animates it to
// where collaborators have since moved it. The persistence and the diff are
// plain data work with no SwiftUI in them, so they live here; the view keeps
// only the animation state.

/// Per-user, per-project record of the column each ticket sat in the last time
/// this user looked at the board.
///
/// Per-USER as well as per-project so each collaborator's unread state is
/// isolated even if two accounts share one app install. Changing the key format
/// from the old project-only form harmlessly re-baselines once (no false unread
/// flags) — see `KanbanReplay.evaluate`'s `.baseline` case.
struct KanbanLastSeenStore {
    let userId: String
    let projectId: String

    /// The single place the key format is spelled. It used to be built by three
    /// separate call sites in the view.
    private var key: String { "kanban-lastseen-\(userId)-\(projectId)" }

    func load() -> [String: String] {
        UserDefaults.standard.dictionary(forKey: key) as? [String: String] ?? [:]
    }

    func save(_ map: [String: String]) {
        UserDefaults.standard.set(map, forKey: key)
    }

    /// Advance one ticket's baseline to `column`, leaving every other ticket's
    /// baseline alone. This is the ONLY way a card leaves its baseline — which
    /// is what makes the yellow ring persist across reloads and relaunches
    /// until this specific collaborator opens the card.
    func record(taskId: String, column: String) {
        var map = load()
        map[taskId] = column
        save(map)
    }
}

/// The board-open diff: what moved, what's new, and whether to replay at all.
enum KanbanReplay {

    struct Plan {
        /// taskId → the column to DISPLAY during the replay (its last-seen one).
        let overrides: [String: String]
        /// taskIds moved or added since this user last looked — these get the
        /// yellow ring until the user opens each card.
        let changedIds: Set<String>
    }

    enum Outcome {
        /// First time this user has ever opened this board. The caller persists
        /// `current` silently so nothing is spuriously flagged unread.
        case baseline
        /// Nothing moved and nothing is new — no animation.
        case unchanged
        case replay(Plan)
    }

    static func evaluate(current: [String: String], lastSeen: [String: String]) -> Outcome {
        guard !lastSeen.isEmpty else { return .baseline }

        var overrides: [String: String] = [:]
        var changed: Set<String> = []
        for (tid, col) in current {
            if let old = lastSeen[tid] {
                if old != col {                       // moved
                    overrides[tid] = old
                    changed.insert(tid)
                }
            } else {
                changed.insert(tid)                   // added
            }
        }
        guard !changed.isEmpty else { return .unchanged }
        return .replay(Plan(overrides: overrides, changedIds: changed))
    }
}
