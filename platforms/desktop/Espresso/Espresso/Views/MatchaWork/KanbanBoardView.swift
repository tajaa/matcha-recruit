import SwiftUI
import UniformTypeIdentifiers
import AppKit

/// The project kanban board: columns, cards, drag-to-move, and the sheets they
/// open. State + body live here; the rendering is split across siblings:
///   • KanbanBoardView+Columns.swift — the columns, cards, and inline add
///   • KanbanBoardView+Toolbar.swift — mode picker + pipeline summary bar
///   • KanbanColumns.swift           — the column vocabulary (module-wide)
///   • KanbanReplay.swift            — last-seen persistence + the open diff
///
/// Members the extensions touch are internal rather than `private`, the same
/// arrangement `TaskViewerSheet` uses for its four extension files.
struct KanbanBoardView: View {
    @Environment(AppState.self) var appState
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var editingTask: MWProjectTask?
    /// Read-only viewer modal. Tapping a card opens this first; the user
    /// clicks "Edit" inside the viewer to escalate to `editingTask`. Keeps
    /// passive viewing from accidentally entering edit mode.
    @State var viewingTask: MWProjectTask?
    /// Card right-click → Delete target; drives the confirmation dialog.
    @State var taskToDelete: MWProjectTask?
    /// Inline-add: which column has its inline TextField visible. Set by the
    /// `+` button on the column header; cleared by Esc / blur / submit.
    @State var inlineAddColumn: String?
    @State var inlineAddTitle: String = ""
    @State var hoveredEmptyColumn: String?
    @State private var searchText = ""
    /// Done column collapses to the 5 most-recently-completed; expand shows all.
    @State var doneExpanded = false
    /// Done column policy. `true` (default): the column resets every Monday and
    /// shows only what was finished this Pacific week — otherwise the board's
    /// completed pile grows without bound and buries the week's actual wins.
    /// `false`: the all-time cumulative list, capped at 5 with a "show more".
    /// Either way nothing is archived or deleted — the expander reveals the
    /// rest, and the cards stay in `done` on the server.
    @AppStorage("kanban-done-weekly-reset") var doneWeeklyReset = true
    /// AI ticket drafting (natural language → reviewable draft).
    @State private var aiDrafting = false
    @State private var aiDraft: MWTaskDraft?
    @State private var showAIReview = false
    @State private var aiError: String?
    /// Header model selector (shared with threads/blog via the same AppStorage key).
    @AppStorage("mw-model") private var selectedModelId = "flash"
    private var selectedModelValue: String? {
        mwModelOptions.first { $0.id == selectedModelId }?.value
    }
    /// Template-compose sheet. `newTaskColumn` is the destination column;
    /// `composeTemplate` the picked template (scaffold + default priority +
    /// category). Reuses the single legacy sheet slot to avoid a 4th `.sheet`.
    @State var newTaskColumn: String?
    @State var composeTemplate: KanbanTemplate?
    /// Sales-pipeline: which stage column's "New Deal" form is open (set by the
    /// `+` button; nil = closed).
    @State var dealComposeColumn: String?
    /// Bumped every 60s so card header aging tints (orange >6h / red >12h)
    /// advance on a board left open, not just on task events / reloads.
    @State private var agingClock = Date()
    /// Board/Pipeline tab — initialized from project.pipelineMode on appear.
    @State var viewMode: KanbanViewMode = .board
    /// Linear list rendering of the same tickets (columns become sections,
    /// with a Mine filter). Persisted so the preference sticks across mounts.
    @AppStorage("mw-kanban-list-layout") var showListView = false

    // MARK: - "Replay changes" on open
    // When the board opens, briefly show each ticket where it was the LAST time
    // this user looked, then animate it to where collaborators have since moved
    // it — so the diff plays out like pieces sliding across a board. Newly-added
    // tickets get a fading highlight. Board mode only. The persistence and diff
    // live in KanbanReplay.swift; what's left here is the animation state.
    /// taskId → the column to DISPLAY during the replay (its last-seen column).
    /// Empty in steady state — grouping then falls straight through to the
    /// memoized `groupedColumns`, so there's zero per-frame cost when idle.
    @State private var replayOverrides: [String: String] = [:]
    /// taskIds moved or added since this user last looked — outlined in yellow
    /// until the user clicks the card to view its updated state (then removed).
    @State var changedIds: Set<String> = []
    /// One replay per board mount; set once tasks first load.
    @State private var didReplay = false
    /// Drives matchedGeometryEffect so a card glides from its old column to its
    /// new one when `replayOverrides` clears.
    @Namespace var cardNS
    /// Skippable how-to for the review/complete workflow — auto-shown once, and
    /// re-openable from the board's "?" button.
    @State private var showReviewGuide = false

    var isPipeline: Bool { viewMode == .pipeline }
    var pipelineSummary: PipelineSummary { PipelineSummary(tasks: viewModel.tasks) }

    // MARK: - Replay helpers

    private func lastSeenStore(_ pid: String) -> KanbanLastSeenStore {
        KanbanLastSeenStore(userId: appState.currentUser?.id ?? "anon", projectId: pid)
    }

    /// Tasks to render in `key`, accounting for an active replay. Steady state
    /// (no overrides) returns the memoized column list unchanged — no extra work
    /// on the resize-driven body re-evals the perf fix guards against.
    func displayTasks(forColumn key: String) -> [MWProjectTask] {
        let grouped = viewModel.groupedColumns(pipeline: isPipeline, search: searchText)
        guard !replayOverrides.isEmpty else { return grouped[key] ?? [] }
        // Re-bucket by display column = override (old column) ?? real column.
        var result = (grouped[key] ?? []).filter { replayOverrides[$0.id] == nil }
        for (col, tasks) in grouped where col != key {
            result += tasks.filter { replayOverrides[$0.id] == key }
        }
        return result
    }

    /// Run once after tasks first load: diff the board against what this user
    /// last saw, stage the old positions, then spring them to current.
    private func maybeReplay() {
        guard !didReplay, !isPipeline, !viewModel.tasks.isEmpty,
              let pid = viewModel.project?.id else { return }
        didReplay = true

        let current = Dictionary(viewModel.tasks.map { ($0.id, $0.boardColumn) },
                                 uniquingKeysWith: { a, _ in a })
        let store = lastSeenStore(pid)
        switch KanbanReplay.evaluate(current: current, lastSeen: store.load()) {
        case .baseline:
            // First time this user ever opens the board: establish the baseline
            // silently so nothing is spuriously flagged unread. After that we
            // NEVER re-baseline the whole board — a card only leaves its
            // baseline column when this user actually opens it (`acknowledge`).
            store.save(current)
        case .unchanged:
            break
        case .replay(let plan):
            replayOverrides = plan.overrides
            // Outline everything that moved or is new in yellow; the ring
            // persists until the user clicks each card to acknowledge it.
            changedIds = plan.changedIds
            Task { @MainActor in
                // Hold the old layout a beat so the eye registers it, then glide.
                try? await Task.sleep(for: .seconds(0.55))
                withAnimation(.spring(response: 0.6, dampingFraction: 0.78)) {
                    replayOverrides = [:]
                }
            }
        }
    }

    /// Mark a card as seen by THIS user: drop its yellow ring and advance its
    /// persisted baseline to the current column. This is the ONLY thing that
    /// clears unread — so an untouched card stays highlighted no matter what
    /// state changes happen elsewhere, until this collaborator opens it.
    func acknowledge(_ taskId: String) {
        if changedIds.contains(taskId) {
            withAnimation(.easeOut(duration: 0.25)) { _ = changedIds.remove(taskId) }
        }
        guard let pid = viewModel.project?.id,
              let task = viewModel.tasks.first(where: { $0.id == taskId }) else { return }
        // Opening = seen everything on the card → also clear the unviewed-updates
        // ring eagerly (the viewer's loadHistory marks these viewed too, but this
        // drops the ring the instant the card is opened, not after the fetch).
        TicketUpdatesStore.shared.markAllViewed(taskId: taskId, eventIds: task.recentEventIds ?? [])
        lastSeenStore(pid).record(taskId: taskId, column: task.boardColumn)
    }

    /// This user moved the card themselves → record it as "seen" at its new
    /// column so the replay diff on the next board open doesn't re-flag (and
    /// re-animate) their own move with a yellow ring. By definition a reviewer
    /// who drags a ticket to Done has already looked at it. The unviewed-updates
    /// side is handled server-side — the viewer's own history events are excluded
    /// from the card's recent_event_ids.
    func noteSelfMove(_ taskId: String, to column: String) {
        if changedIds.contains(taskId) {
            _ = changedIds.remove(taskId)
        }
        guard let pid = viewModel.project?.id else { return }
        lastSeenStore(pid).record(taskId: taskId, column: column)
    }

    /// Open a ticket's viewer when chat asked us to (a ticket chip click /
    /// "Go to ticket"). Waits until the task is loaded, then clears the request.
    private func openPendingTaskIfPossible() {
        guard let tid = appState.pendingOpenTaskId,
              let task = viewModel.tasks.first(where: { $0.id == tid }) else { return }
        acknowledge(tid)
        viewingTask = task
        appState.pendingOpenTaskId = nil
    }

    // MARK: - Body

    var body: some View {
        boardSheets(boardContent)
    }

    private var boardContent: some View {
        VStack(spacing: 0) {
            if let err = viewModel.errorMessage {
                errorBanner(err)
            }
            if viewModel.isLoadingTasks && viewModel.tasks.isEmpty {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else {
                if !viewModel.tasks.isEmpty {
                    searchRow
                    TaskProgressBar(tasks: viewModel.tasks, compact: true)
                        .padding(.horizontal, 12)
                        .padding(.top, 4)
                        .padding(.bottom, 4)
                }
                boardPipelinePicker
                if isPipeline {
                    pipelineSummaryBar
                } else {
                    AIComposeBar(isDrafting: aiDrafting, error: aiError) { submitAIDraft(prompt: $0) }
                }
                if showListView {
                    KanbanListView(
                        viewModel: viewModel,
                        isPipeline: isPipeline,
                        searchText: searchText,
                        myUserId: appState.currentUser?.id ?? "",
                        onOpen: { task in
                            acknowledge(task.id)
                            viewingTask = task
                        }
                    )
                } else {
                    boardColumns
                }
            }
        }
        .background(ThemeRadialBackground())
        .onAppear {
            if viewModel.project?.pipelineMode == true { viewMode = .pipeline }
            TicketUpdatesStore.shared.configure(
                userId: appState.currentUser?.id, projectId: viewModel.project?.id)
            maybeReplay()
            openPendingTaskIfPossible()
            // First collab-board open ever → show the review how-to once.
            if viewModel.project?.projectType == "collab",
               !UserDefaults.standard.bool(forKey: ReviewGuideWizard.seenKey) {
                showReviewGuide = true
            }
        }
        .task {
            if viewModel.tasks.isEmpty {
                await viewModel.loadTasks()
            }
            // A cumulative Done column needs the cards the week-scoped load
            // withheld. Weekly boards fetch them only if the user expands.
            if !doneWeeklyReset && !isPipeline {
                await viewModel.loadAllDoneTasks()
            }
            // Auto-pick up merged commits → subtask check-offs (gated 10-min
            // cooldown; no-op if no repo connected). "Done = merged."
            await viewModel.autoScanCommitsIfStale()
            // Always reload from the server too: the push webhook scans
            // server-side on merge, so suggestions can exist even when the
            // auto-scan above short-circuits on its cooldown. Without this the
            // card badges wouldn't appear until a manual scan.
            await viewModel.loadCommitSuggestions()
        }
        // Tasks usually arrive after the board mounts — run the replay the
        // moment they do (maybeReplay is idempotent, guarded by didReplay), and
        // honor any pending "open this ticket" request from chat.
        .onChange(of: viewModel.tasks.isEmpty) { _, empty in
            if !empty { maybeReplay(); openPendingTaskIfPossible() }
        }
        .onChange(of: appState.pendingOpenTaskId) { _, _ in
            openPendingTaskIfPossible()
        }
        // Switching Done to cumulative mid-session: pull the earlier finishes
        // the week-scoped load left on the server.
        .onChange(of: doneWeeklyReset) { _, weekly in
            if !weekly { Task { await viewModel.loadAllDoneTasks() } }
        }
        // Re-render once a minute so aging tints advance while the board sits
        // open. Cards carry closures (non-equatable), so the parent re-render
        // re-renders them and recomputes task.aging against the current time.
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { now in
            agingClock = now
        }
    }

    // MARK: - Header rows

    private func errorBanner(_ err: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 11))
                .foregroundColor(.red)
            Text(err)
                .font(.system(size: 11))
                .foregroundColor(.white)
                .lineLimit(2)
            Spacer()
            Button {
                viewModel.errorMessage = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.red.opacity(0.15))
    }

    private var searchRow: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            // Short placeholder — the long syntax-hint version forced the row
            // past a narrow split pane's width (clipped the help button +
            // progress counter). Syntax lives in .help.
            TextField("Search tasks…", text: $searchText)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .frame(maxWidth: .infinity)
                .help("space = AND, \"quotes\" = exact phrase")
            if !searchText.isEmpty {
                Button { searchText = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            Button { showReviewGuide = true } label: {
                Image(systemName: "questionmark.circle")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("How reviewing & completing tickets works")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Sheets
    //
    // Seven presentations, lifted off `body` so the layout reads in one screen.
    // A function taking the content rather than a `@ViewBuilder var` because
    // presentation modifiers chain onto a view — they don't compose as content.
    // Stays in this file: every one of them drives `private` state.
    private func boardSheets<Content: View>(_ content: Content) -> some View {
        content
            .sheet(isPresented: $showReviewGuide) {
                ReviewGuideWizard(onClose: { showReviewGuide = false })
            }
            .confirmationDialog(
                "Delete this task?",
                isPresented: Binding(
                    get: { taskToDelete != nil },
                    set: { if !$0 { taskToDelete = nil } }
                ),
                presenting: taskToDelete
            ) { task in
                Button("Delete", role: .destructive) {
                    let id = task.id
                    taskToDelete = nil
                    Task { await viewModel.deleteTask(id: id) }
                }
                Button("Cancel", role: .cancel) { taskToDelete = nil }
            } message: { task in
                Text("\"\(task.title)\" will be permanently removed. This cannot be undone.")
            }
            .sheet(item: $viewingTask) { task in
                TaskViewerSheet(
                    task: task,
                    viewModel: viewModel,
                    onEdit: {
                        // Open editor on the next runloop turn so SwiftUI
                        // processes the viewer-dismiss before the editor-set
                        // — otherwise the new sheet can race the dismiss
                        // animation and flicker.
                        let target = task
                        viewingTask = nil
                        DispatchQueue.main.async {
                            editingTask = target
                        }
                    },
                    onClose: { viewingTask = nil }
                )
                // Opening the ticket = seen → clear its notifications from the
                // bell and the project tab badge.
                .onAppear { appState.markTicketSeen(taskId: task.id) }
            }
            .sheet(item: $editingTask) { task in
                TaskEditorSheet(
                    task: task,
                    viewModel: viewModel,
                    onSave: { patch in
                        Task {
                            await viewModel.updateTask(id: task.id, patch: patch)
                            editingTask = nil
                        }
                    },
                    onDelete: {
                        Task {
                            await viewModel.deleteTask(id: task.id)
                            editingTask = nil
                        }
                    },
                    onClose: {
                        editingTask = nil
                    }
                )
            }
            .sheet(isPresented: Binding(get: { newTaskColumn != nil }, set: { if !$0 { newTaskColumn = nil; composeTemplate = nil } })) {
                if let col = newTaskColumn {
                    TaskComposeContent(
                        column: col,
                        template: composeTemplate ?? .general,
                        viewModel: viewModel,
                        onClose: { newTaskColumn = nil; composeTemplate = nil }
                    )
                }
            }
            .sheet(isPresented: Binding(get: { dealComposeColumn != nil }, set: { if !$0 { dealComposeColumn = nil } })) {
                if let col = dealComposeColumn {
                    DealComposeContent(
                        stageKey: col,
                        stageLabel: columnsFor(mode: .pipeline).first(where: { $0.key == col })?.label ?? "Lead",
                        viewModel: viewModel,
                        onClose: { dealComposeColumn = nil }
                    )
                }
            }
            .sheet(isPresented: $showAIReview) {
                if let draft = aiDraft {
                    AIDraftReviewSheet(
                        draft: draft,
                        collaborators: viewModel.collaborators,
                        elements: viewModel.elements,
                        onCreate: { title, column, priority, assignedTo, description, category, elementId, subtasks in
                            await viewModel.addTask(
                                title: title, column: column, priority: priority,
                                assignedTo: assignedTo, description: description,
                                category: category, elementId: elementId, subtasks: subtasks
                            )
                        },
                        onClose: { showAIReview = false; aiDraft = nil }
                    )
                }
            }
    }

    // MARK: - AI drafting

    private func submitAIDraft(prompt: String) {
        let prompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, !aiDrafting, let pid = viewModel.project?.id else { return }
        aiDrafting = true
        aiError = nil
        Task {
            do {
                let draft = try await MatchaWorkService.shared.draftTaskFromPrompt(projectId: pid, prompt: prompt, model: selectedModelValue)
                await MainActor.run {
                    aiDrafting = false
                    aiDraft = draft
                    showAIReview = true
                }
            } catch {
                await MainActor.run {
                    aiDrafting = false
                    if case APIError.httpError(let code, _) = error, code == 429 {
                        aiError = "AI drafting limit reached. Create tickets manually or try again later."
                    } else if case APIError.httpError(let code, _) = error, code == 402 {
                        aiError = "This workspace has reached its AI token budget."
                    } else {
                        aiError = "Couldn't draft that — try rephrasing."
                    }
                }
            }
        }
    }
}
