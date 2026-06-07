import Foundation
import AppKit
import UniformTypeIdentifiers

struct CollabActivityItem: Identifiable, Hashable {
    let id = UUID()
    let icon: String
    let text: String
    let timestamp: Date
}

@Observable
class ProjectDetailViewModel {
    var project: MWProject?
    var activeChatId: String?
    var isLoading = false
    var errorMessage: String?
    var tasks: [MWProjectTask] = [] {
        didSet { tasksVersion &+= 1 }   // invalidates the grouped-column cache
    }
    var isLoadingTasks = false
    var files: [MWProjectFile] = []
    var folders: [MWProjectFolder] = []
    var links: [MWProjectLink] = []
    var isLoadingFiles = false
    var collaborators: [MWProjectCollaborator] = []
    var elements: [MWProjectElement] = []
    /// Attachments per task, keyed by task id. Seeded by `loadTasks`
    /// (server embeds `attachments` per task) and updated by add/delete.
    var taskFiles: [String: [MWProjectFile]] = [:]
    /// Checklist items per task, keyed by task id. Loaded lazily when a task
    /// viewer opens; mutated optimistically. `syncSubtaskCounts` mirrors the
    /// counts onto the matching `tasks` entry so the card face updates live.
    var taskSubtasks: [String: [MWSubtask]] = [:]
    /// Pending commit→subtask suggestions for the current project, keyed by
    /// task id. Filled by `scanCommits()` / `loadCommitSuggestions()`; the
    /// TaskViewer checklist renders a chip per matching subtask.
    var commitSuggestions: [String: [MWCommitSuggestion]] = [:]
    /// 1-click AI ticket summaries, keyed by task id. Session-ephemeral (the
    /// server doesn't persist them) — a fresh click regenerates.
    var taskSummaries: [String: String] = [:]
    var isScanningCommits = false
    /// One-line result of the last scan ("3 commits · 2 suggestions"), shown
    /// transiently in the Elements header.
    var lastScanSummary: String?
    /// Repo-snapshot sync (uploads element code text for Prop grounding).
    var isSyncingRepo = false
    var lastSyncSummary: String?
    /// Per-project last auto-sync time → cooldown so opening the Props tab
    /// repeatedly never spams GitHub. In-memory on the (cached) VM, so it
    /// survives tab switches. Manual Sync bypasses it.
    var lastGitHubSyncAt: [String: Date] = [:]
    /// Per-project last commit-scan time → cooldown for auto-scan on Kanban open.
    var lastGitHubScanAt: [String: Date] = [:]
    let githubSyncCooldown: TimeInterval = 600  // 10 min
    /// Per-session activity log surfaced in the collab Overview panel. Capped
    /// at 20 entries; FIFO eviction. In-memory only — survives panel switches
    /// but not project switches or app relaunches. Backend feed is a follow-up.
    var recentActivity: [CollabActivityItem] = []

    /// subtaskId → the accepted commit that completed it (latest). Loaded for the
    /// in-review audit so a reviewer can see + overturn the AI auto-checks.
    var commitCompletions: [String: MWCommitSuggestion] = [:]

    let service = MatchaWorkService.shared
    // Per-project "last fetched" stamps so a tab re-entry within 30s is a no-op:
    // the per-entity service cache + these in-memory arrays are already fresh,
    // and the project WS pushes task deltas live. Keyed by projectId.
    var lastFilesFetch: [String: Date] = [:]
    var lastLinksFetch: [String: Date] = [:]
    var lastChatSyncFetch: [String: Date] = [:]
    func isFresh(_ map: [String: Date], _ pid: String, within: TimeInterval = 30) -> Bool {
        if let t = map[pid] { return Date().timeIntervalSince(t) < within }
        return false
    }
    /// Logged-in user — used to suppress self-echoes from the project WS
    /// task event fan-out (we already applied the change optimistically).
    var currentUserId: String?

    // ── Grouped-column cache ──────────────────────────────────────────────
    // The kanban board's `columnView` lives inside a GeometryReader that
    // re-evaluates every frame during a window-resize drag. Filtering, sorting,
    // and ISO-date-parsing the task list per column per frame pinned resize to
    // ~11fps. `groupedColumns` memoizes the fully-ordered per-column arrays and
    // only recomputes when (tasks, search, mode) actually change — a resize is
    // a cache hit. `@ObservationIgnored` so writing the cache during view-body
    // evaluation neither triggers observation nor trips "modifying state during
    // view update".
    @ObservationIgnored private var tasksVersion = 0
    @ObservationIgnored private var groupKey: (v: Int, pipeline: Bool, search: String)?
    @ObservationIgnored private var groupValue: [String: [MWProjectTask]] = [:]

    /// Tasks grouped by board/pipeline column key, each bucket in final display
    /// order (priority desc, then oldest-waiting first; the `done` bucket is
    /// pre-sorted most-recently-completed first). Tasks whose column isn't a
    /// known key fall into the first column. Memoized — see the note above.
    func groupedColumns(pipeline: Bool, search: String) -> [String: [MWProjectTask]] {
        if let k = groupKey, k.v == tasksVersion, k.pipeline == pipeline, k.search == search {
            return groupValue
        }
        let cols = pipeline ? SalesStage.columns : kanbanColumns
        let colKeys = Set(cols.map { $0.key })
        let firstKey = cols.first?.key
        let tokens = KanbanSearch.tokens(search)

        // Parse each task's createdAt exactly once (vs. twice per comparison in
        // an O(n log n) sort).
        var created: [String: Date] = [:]
        created.reserveCapacity(tasks.count)
        for t in tasks { created[t.id] = PacificDateFormatter.parse(t.createdAt) ?? .distantFuture }

        var out: [String: [MWProjectTask]] = [:]
        for t in tasks where KanbanSearch.matches(t, tokens: tokens) {
            let raw = pipeline ? (t.pipelineColumn ?? "lead") : t.boardColumn
            let key = colKeys.contains(raw) ? raw : (firstKey ?? raw)
            out[key, default: []].append(t)
        }
        for (k, bucket) in out {
            out[k] = bucket.sorted {
                // Seriousness dictates order: critical → high → medium → low.
                // Secondary: oldest-waiting first within a priority bucket, so
                // the longest-pending (and reddest) card floats to the top.
                if $0.priorityRank != $1.priorityRank { return $0.priorityRank < $1.priorityRank }
                return (created[$0.id] ?? .distantFuture) < (created[$1.id] ?? .distantFuture)
            }
        }
        // Done column collapses to the 5 most-recently-completed (newest first);
        // sort that bucket by completion instead of the priority/age order.
        if !pipeline, var done = out["done"] {
            done.sort {
                (PacificDateFormatter.parse($0.completedAt ?? $0.updatedAt ?? $0.createdAt) ?? .distantPast)
                > (PacificDateFormatter.parse($1.completedAt ?? $1.updatedAt ?? $1.createdAt) ?? .distantPast)
            }
            out["done"] = done
        }

        groupKey = (tasksVersion, pipeline, search)
        groupValue = out
        return out
    }

    func logActivity(_ icon: String, _ text: String) {
        recentActivity.insert(
            CollabActivityItem(icon: icon, text: text, timestamp: Date()),
            at: 0
        )
        if recentActivity.count > 20 {
            recentActivity.removeLast(recentActivity.count - 20)
        }
    }
}
