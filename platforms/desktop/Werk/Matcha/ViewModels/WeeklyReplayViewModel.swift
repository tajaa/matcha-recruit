import Foundation

/// Drives the Weekly Work Replay tab: fetches one week's board snapshot +
/// history events, folds them forward to a scrub position, and runs the
/// play/pause timer. Deliberately separate from `ProjectDetailViewModel` —
/// this is read-only, self-contained state (current week, scrub position,
/// playing/paused) that has nothing to do with live task mutation.
@Observable
final class WeeklyReplayViewModel {
    let projectId: String
    private let service = MatchaWorkService.shared

    /// Monday 00:00 Pacific of the week currently shown.
    private(set) var weekStart: Date
    var weekLabel: String { PacificDateFormatter.weekLabel(weekStart) }

    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var replay: MWWeeklyReplay?

    /// How many events (from `replay.events`, in order) have been folded in.
    /// 0 = just the starting snapshot; `events.count` = caught up to week end.
    private(set) var scrubIndex: Int = 0
    private(set) var isPlaying = false
    private var playTask: Task<Void, Never>?

    /// Folded board state at `scrubIndex`, keyed by task id. Recomputed
    /// on every scrub/play tick — event counts per week are small (dozens,
    /// not thousands), so a full refold is cheap and avoids incremental-state
    /// bugs from applying events out of order.
    private(set) var currentState: [String: ReplayTaskState] = [:]

    /// `currentState` in a STABLE order. A Dictionary's `.values` order is
    /// unspecified and changes across rebuilds, which reshuffles the board's
    /// ForEach every fold step and defeats `matchedGeometryEffect`'s card
    /// tracking. Sorting by id gives each card a fixed slot so a column change
    /// is the only movement the animation has to express.
    var orderedTasks: [ReplayTaskState] {
        currentState.values.sorted { $0.id < $1.id }
    }

    /// The card the event at `scrubIndex` just moved between columns, if any.
    /// The board lifts it (scale + shadow + z-order) for the duration of its
    /// glide so the transition reads as a drag rather than a teleport, then
    /// `dropLiftTask` clears it to land the card.
    private(set) var movingTaskId: String?
    private var dropLiftTask: Task<Void, Never>?

    /// How long a card stays "picked up" after the move that triggered it.
    /// Matches the board's glide spring — the lift drops as the card lands.
    private static let liftDuration = Duration.milliseconds(520)

    /// Tally of the events folded in so far — climbs as the week plays.
    private(set) var stats = ReplayStats()

    /// Pacific time label for the current scrub position, e.g. "Tue 2:14 PM".
    var currentMomentLabel: String? {
        guard let replay else { return nil }
        if scrubIndex == 0 { return PacificDateFormatter.absolute(replay.weekStart) }
        let event = replay.events[scrubIndex - 1]
        guard let time = PacificDateFormatter.timeOnly(event.createdAt) else { return nil }
        let day = PacificDateFormatter.shortDate(event.createdAt) ?? ""
        return "\(day), \(time)"
    }

    var eventCount: Int { replay?.events.count ?? 0 }

    init(projectId: String) {
        self.projectId = projectId
        self.weekStart = PacificDateFormatter.startOfWeek(containing: Date())
        Task { await load() }
    }

    deinit {
        playTask?.cancel()
        dropLiftTask?.cancel()
    }

    // MARK: - Week navigation

    func previousWeek() { changeWeek(by: -1) }
    func nextWeek() { changeWeek(by: 1) }

    private func changeWeek(by weeks: Int) {
        pause()
        weekStart = PacificDateFormatter.addWeeks(weeks, to: weekStart)
        scrubIndex = 0
        Task { await load() }
    }

    // MARK: - Fetch

    @MainActor
    func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        let iso = ISO8601DateFormatter().string(from: weekStart)
        do {
            let result = try await service.fetchWeeklyReplay(projectId: projectId, weekStart: iso)
            replay = result
            scrubIndex = 0
            recomputeState()
        } catch {
            print("[WeeklyReplay] load failed project=\(projectId) week_start=\(iso): \(error)")
            loadError = "Couldn't load this week's history."
            replay = nil
            currentState = [:]
            stats = ReplayStats()
        }
    }

    // MARK: - Scrub + playback

    /// Jump directly to an event index (used by the draggable scrubber, which
    /// maps a drag position to the nearest event and snaps to it).
    /// No lift: a scrub can cross dozens of events at once, and picking up
    /// whichever card the playhead happened to land on would strobe.
    func scrub(to index: Int) {
        guard let replay else { return }
        scrubIndex = max(0, min(index, replay.events.count))
        recomputeState()
    }

    func togglePlay() {
        isPlaying ? pause() : play()
    }

    func play() {
        guard let replay, !replay.events.isEmpty else { return }
        // Restart from the top if already caught up, so hitting Play after a
        // full run replays instead of doing nothing.
        if scrubIndex >= replay.events.count { scrubIndex = 0; recomputeState() }
        isPlaying = true
        // Fixed total playback duration, divided across events with a floor
        // per-step — a quiet week doesn't feel instant, a busy week doesn't
        // drag on for minutes. The floor also has to outlast the board's
        // glide spring, or a busy week retargets each card mid-flight and the
        // moves read as jitter instead of drags.
        let totalMs = 22_000.0
        let stepMs = max(320.0, totalMs / Double(replay.events.count))
        playTask?.cancel()
        playTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(Int(stepMs)))
                if Task.isCancelled { return }
                await MainActor.run {
                    guard self.isPlaying, let replay = self.replay else { return }
                    if self.scrubIndex >= replay.events.count {
                        self.isPlaying = false
                        self.playTask?.cancel()
                        return
                    }
                    self.scrubIndex += 1
                    self.recomputeState(liftLastMove: true)
                }
            }
        }
    }

    func pause() {
        isPlaying = false
        playTask?.cancel()
        playTask = nil
        clearLift()
    }

    // MARK: - Fold

    private func recomputeState(liftLastMove: Bool = false) {
        guard let replay else { currentState = [:]; clearLift(); return }
        var state: [String: ReplayTaskState] = [:]
        for t in replay.startingState {
            guard let taskId = t.taskId else { continue }
            state[taskId] = ReplayTaskState(
                id: taskId, title: t.title, column: t.column,
                assigneeName: t.assigneeName, assigneeAvatarUrl: t.assigneeAvatarUrl,
            )
        }
        let applied = replay.events.prefix(scrubIndex)
        for event in applied {
            guard let taskId = event.taskId else { continue }
            switch event.eventType {
            case "created":
                state[taskId] = ReplayTaskState(id: taskId, title: event.title, column: event.toColumn ?? "todo")
            case "column_change", "review_rejected", "review_approved":
                guard let column = event.toColumn else { break }
                if state[taskId] != nil {
                    state[taskId]?.column = column
                } else {
                    // Unknown task: it sat in Done before the week began, so the
                    // server didn't seed it (Done resets weekly), and now it's
                    // been reopened. Materialize it from the event so the card
                    // reappears where it was dragged to.
                    state[taskId] = ReplayTaskState(id: taskId, title: event.title, column: column)
                }
            case "deleted":
                state[taskId]?.isDeleted = true
            default:
                break
            }
        }
        currentState = state
        stats = Self.tally(Array(applied))

        if liftLastMove, let moved = lastMovedTaskId(in: replay), state[moved] != nil {
            setLift(moved)
        } else {
            clearLift()
        }
    }

    /// Count what the events say the team did. Every event type the board
    /// ignores (`assignee_change`, `description_change`, `round_started`, …)
    /// still counts toward its author's contribution total — they're real work,
    /// just not board-column work.
    private static func tally(_ events: [MWReplayEvent]) -> ReplayStats {
        var stats = ReplayStats()
        var byActor: [String: (name: String, avatar: String?, count: Int)] = [:]

        for event in events {
            switch event.eventType {
            case "created":
                stats.created += 1
            case "column_change", "review_approved":
                guard event.fromColumn != event.toColumn else { break }
                stats.moved += 1
                if event.toColumn == "done" { stats.completed += 1 }
            case "review_rejected":
                guard event.fromColumn != event.toColumn else { break }
                stats.moved += 1
                stats.sentBack += 1
            case "deleted":
                stats.deleted += 1
            case "subtask_added":
                stats.subtasksAdded += 1
            case "subtask_completed":
                stats.subtasksCompleted += 1
            default:
                break
            }

            // Fall back to the actor's id when the name joins came up empty
            // (deleted user, or a row written by a system path with no actor
            // name) so their work still lands under one identity.
            guard let actorId = event.actorId else { continue }
            let name = event.actorName ?? "Unknown"
            let prior = byActor[actorId]?.count ?? 0
            byActor[actorId] = (name, event.actorAvatarUrl, prior + 1)
        }

        stats.contributors = byActor
            .map { ReplayContributor(id: $0.key, name: $0.value.name,
                                     avatarUrl: $0.value.avatar, eventCount: $0.value.count) }
            // Name as tiebreak: a Dictionary iterates in an unspecified order,
            // so equal counts would otherwise reshuffle the strip every tick.
            .sorted { ($0.eventCount, $1.name) > ($1.eventCount, $0.name) }
        return stats
    }

    /// The task the event at `scrubIndex` carried across columns, or nil if
    /// that event wasn't a move (creation, deletion, comment, subtask, …) or
    /// left the card in the column it was already in.
    private func lastMovedTaskId(in replay: MWWeeklyReplay) -> String? {
        guard scrubIndex > 0, scrubIndex <= replay.events.count else { return nil }
        let event = replay.events[scrubIndex - 1]
        guard ["column_change", "review_rejected", "review_approved"].contains(event.eventType),
              let taskId = event.taskId,
              let to = event.toColumn,
              event.fromColumn != to
        else { return nil }
        return taskId
    }

    /// Pick the card up. Cancels any in-flight drop so a rapid second move
    /// hands the lift straight to the new card instead of landing the old one.
    private func setLift(_ taskId: String) {
        dropLiftTask?.cancel()
        movingTaskId = taskId
        dropLiftTask = Task { [weak self] in
            try? await Task.sleep(for: Self.liftDuration)
            guard !Task.isCancelled else { return }
            await MainActor.run { [weak self] in
                guard let self, self.movingTaskId == taskId else { return }
                self.movingTaskId = nil
            }
        }
    }

    private func clearLift() {
        dropLiftTask?.cancel()
        dropLiftTask = nil
        movingTaskId = nil
    }
}
