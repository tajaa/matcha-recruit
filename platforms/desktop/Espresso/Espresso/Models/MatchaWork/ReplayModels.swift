import Foundation

/// Wire response for `GET /projects/{id}/history/replay?week_start=...`.
/// `startingState` is the board's column layout as of `weekStart` (one row
/// per task that already existed); `events` are every history row within the
/// 7-day window, ascending, for `WeeklyReplayViewModel` to fold forward.
struct MWWeeklyReplay: Codable {
    let weekStart: String
    let weekEnd: String
    let startingState: [MWReplayStartingTask]
    let events: [MWReplayEvent]

    enum CodingKeys: String, CodingKey {
        case weekStart = "week_start"
        case weekEnd = "week_end"
        case startingState = "starting_state"
        case events
    }
}

struct MWReplayStartingTask: Codable {
    /// Nullable defensively: the server excludes null-keyed rows (tasks
    /// hard-deleted before task_id_text existed to survive the delete), but
    /// one unaddressable row shouldn't fail Codable decode for the whole week.
    let taskId: String?
    let title: String
    let column: String
    let assigneeName: String?
    let assigneeAvatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case title, column
        case assigneeName = "assignee_name"
        case assigneeAvatarUrl = "assignee_avatar_url"
    }
}

/// One `mw_task_history` row. `taskId` is the durable `COALESCE(task_id_text,
/// task_id::text)` key from the server — stable even for hard-deleted tickets,
/// see mwtaskhtxt01 migration. Only `created`/`column_change`/
/// `review_rejected`/`review_approved`/`deleted` are acted on by the replay
/// engine; other event types (comments, subtasks, ...) ride along unused for
/// now.
struct MWReplayEvent: Codable, Identifiable {
    let id: String
    let taskId: String?
    let eventType: String
    let fromColumn: String?
    let toColumn: String?
    let actorId: String?
    let actorName: String?
    let actorAvatarUrl: String?
    let title: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case taskId = "task_id"
        case eventType = "event_type"
        case fromColumn = "from_column"
        case toColumn = "to_column"
        case actorId = "actor_id"
        case actorName = "actor_name"
        case actorAvatarUrl = "actor_avatar_url"
        case title
        case createdAt = "created_at"
    }
}

/// What the team did, counted from the replay events folded in so far — so the
/// numbers tick up as the week plays rather than sitting at their end-of-week
/// totals from the first frame.
///
/// `moved` counts every column change, including the ones that also land in
/// `completed` (a move to "done") or `sentBack` (a review rejection): those are
/// facets of a move, not separate events, and the strip reads as
/// "12 moved, 5 of them finished" rather than three disjoint tallies.
struct ReplayStats: Equatable {
    var created = 0
    var moved = 0
    var completed = 0
    var sentBack = 0
    var deleted = 0
    var subtasksAdded = 0
    var subtasksCompleted = 0
    var contributors: [ReplayContributor] = []

    var isEmpty: Bool {
        created == 0 && moved == 0 && deleted == 0
            && subtasksAdded == 0 && subtasksCompleted == 0
    }
}

/// One person's footprint on the week, ranked by how many events they authored.
struct ReplayContributor: Identifiable, Equatable {
    let id: String
    let name: String
    let avatarUrl: String?
    let eventCount: Int
}

/// A card's folded-forward state at some scrub position in the replay —
/// deliberately NOT `MWProjectTask`: the live model is bound to interactive
/// board machinery (drag/menu/WS mutation) that a frozen historical frame
/// has no business touching.
struct ReplayTaskState: Identifiable, Equatable {
    let id: String
    var title: String
    var column: String
    var assigneeName: String?
    var assigneeAvatarUrl: String?
    /// True once a `deleted` event has been folded in at/before the current
    /// scrub position — the card fades out rather than disappearing.
    var isDeleted: Bool = false
}
