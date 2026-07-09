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
