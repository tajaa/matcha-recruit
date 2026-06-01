import Foundation

/// Per-user, per-project record of which ticket "updates" a collaborator has
/// marked viewed. An update = one viewable mw_task_history event (comment,
/// round change, subtask added, column move / send-back) — see the backend's
/// COUNTED_UPDATE_EVENTS, which this set must mirror.
///
/// Drives the kanban card's unviewed-updates badge and the UPDATES checkoff
/// list in the ticket viewer. "Viewed" is intentionally separate from subtask /
/// task completion: completion means the work is done, viewed means the reader
/// has seen the update.
///
/// Client-side only for v1 — persisted in UserDefaults under a per-user,
/// per-project key (so a different login on the same Mac doesn't inherit
/// another user's viewed-state). No backend table, no cross-device sync —
/// matches the yellow-ring baseline model in KanbanBoardView. v2 can move to a
/// per-user read-receipt table if Mac ↔ web sync is wanted.
@MainActor
@Observable
final class TicketUpdatesStore {
    static let shared = TicketUpdatesStore()

    /// Must stay in lock-step with the backend `COUNTED_UPDATE_EVENTS`
    /// (project_task_service.py) so the viewer's UPDATES list length matches
    /// the card badge at baseline.
    static let countedEventTypes: Set<String> = [
        "activity", "round_started", "subtask_added", "column_change", "review_rejected",
    ]

    /// Bumped on every mutation so SwiftUI views observing the store re-render
    /// (the card badge, the viewer list). The maps are private so all mutation
    /// routes through the public API and persistence stays in sync.
    private(set) var generation: Int = 0

    /// taskId → set of viewed event ids.
    private var viewed: [String: Set<String>] = [:]
    private var userId: String?
    private var projectId: String?

    private init() {}

    private func key(_ uid: String, _ pid: String) -> String {
        "ticket-updates-viewed:\(uid):\(pid)"
    }

    /// Bind the store to the current user + project. Loads the persisted map,
    /// or clears when either is missing. Idempotent on the same pair.
    func configure(userId: String?, projectId: String?) {
        guard self.userId != userId || self.projectId != projectId else { return }
        self.userId = userId
        self.projectId = projectId
        if let userId, let projectId,
           let raw = UserDefaults.standard.dictionary(forKey: key(userId, projectId)) as? [String: [String]] {
            viewed = raw.mapValues { Set($0) }
        } else {
            viewed = [:]
        }
        generation &+= 1
    }

    /// First time we see a task (no stored entry), treat every current update as
    /// already viewed so a ticket's pre-existing history isn't flagged as new.
    /// Only genuinely new events that arrive afterward then count as unviewed.
    /// No-op once the task has an entry, or if the task carries no event ids yet.
    func baselineIfNeeded(_ task: MWProjectTask) {
        guard viewed[task.id] == nil, let ids = task.recentEventIds else { return }
        viewed[task.id] = Set(ids)
        persist()
        generation &+= 1
    }

    /// Number of this task's recent update events the user hasn't viewed.
    func unviewedCount(_ task: MWProjectTask) -> Int {
        guard let ids = task.recentEventIds, !ids.isEmpty else { return 0 }
        let seen = viewed[task.id] ?? []
        return ids.reduce(into: 0) { acc, id in if !seen.contains(id) { acc += 1 } }
    }

    func isViewed(taskId: String, eventId: String) -> Bool {
        viewed[taskId]?.contains(eventId) ?? false
    }

    func markViewed(taskId: String, eventId: String) {
        setViewed(taskId: taskId, eventId: eventId, isViewed: true)
    }

    /// Two-way toggle so a mis-tapped row can be un-marked.
    func setViewed(taskId: String, eventId: String, isViewed: Bool) {
        let changed: Bool
        if isViewed {
            changed = viewed[taskId, default: []].insert(eventId).inserted
        } else {
            changed = viewed[taskId]?.remove(eventId) != nil
        }
        guard changed else { return }
        persist()
        generation &+= 1
    }

    func markAllViewed(taskId: String, eventIds: [String]) {
        var set = viewed[taskId] ?? []
        let before = set.count
        set.formUnion(eventIds)
        guard set.count != before else { return }
        viewed[taskId] = set
        persist()
        generation &+= 1
    }

    private func persist() {
        guard let userId, let projectId else { return }
        let encoded = viewed.mapValues { Array($0) }
        UserDefaults.standard.set(encoded, forKey: key(userId, projectId))
    }
}
