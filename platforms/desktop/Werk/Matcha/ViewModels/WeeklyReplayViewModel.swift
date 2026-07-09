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
        }
    }

    // MARK: - Scrub + playback

    /// Jump directly to an event index (used by the draggable scrubber, which
    /// maps a drag position to the nearest event and snaps to it).
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
        // drag on for minutes.
        let totalMs = 22_000.0
        let stepMs = max(150.0, totalMs / Double(replay.events.count))
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
                    self.recomputeState()
                }
            }
        }
    }

    func pause() {
        isPlaying = false
        playTask?.cancel()
        playTask = nil
    }

    // MARK: - Fold

    private func recomputeState() {
        guard let replay else { currentState = [:]; return }
        var state: [String: ReplayTaskState] = [:]
        for t in replay.startingState {
            guard let taskId = t.taskId else { continue }
            state[taskId] = ReplayTaskState(
                id: taskId, title: t.title, column: t.column,
                assigneeName: t.assigneeName, assigneeAvatarUrl: t.assigneeAvatarUrl,
            )
        }
        for event in replay.events.prefix(scrubIndex) {
            guard let taskId = event.taskId else { continue }
            switch event.eventType {
            case "created":
                state[taskId] = ReplayTaskState(id: taskId, title: event.title, column: event.toColumn ?? "todo")
            case "column_change", "review_rejected", "review_approved":
                if let column = event.toColumn {
                    state[taskId]?.column = column
                }
            case "deleted":
                state[taskId]?.isDeleted = true
            default:
                break
            }
        }
        currentState = state
    }
}
