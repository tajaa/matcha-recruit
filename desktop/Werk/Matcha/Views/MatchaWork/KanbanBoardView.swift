import SwiftUI
import UniformTypeIdentifiers
import AppKit

let kanbanColumns: [(key: String, label: String)] = [
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("changes_requested", "Changes Requested"),
    ("done", "Done"),
]

private enum ViewMode { case board, pipeline }

private func columnsFor(mode: ViewMode) -> [(key: String, label: String)] {
    mode == .pipeline ? SalesStage.columns : kanbanColumns
}

func columnsFor(pipeline: Bool) -> [(key: String, label: String)] {
    columnsFor(mode: pipeline ? .pipeline : .board)
}

/// Compact currency for deal values / pipeline totals — "$12k", "$1.2M",
/// "$0" when nil/zero. Pipeline-mode only.
func formatDealValue(_ value: Double) -> String {
    let v = value
    if v >= 1_000_000 { return String(format: "$%.1fM", v / 1_000_000) }
    if v >= 1_000 { return String(format: "$%.0fk", v / 1_000) }
    return String(format: "$%.0f", v)
}

struct KanbanBoardView: View {
    @Environment(AppState.self) private var appState
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var editingTask: MWProjectTask?
    /// Read-only viewer modal. Tapping a card opens this first; the user
    /// clicks "Edit" inside the viewer to escalate to `editingTask`. Keeps
    /// passive viewing from accidentally entering edit mode.
    @State private var viewingTask: MWProjectTask?
    /// Card right-click → Delete target; drives the confirmation dialog.
    @State private var taskToDelete: MWProjectTask?
    /// Inline-add: which column has its inline TextField visible. Set by the
    /// `+` button on the column header; cleared by Esc / blur / submit.
    @State private var inlineAddColumn: String?
    @State private var inlineAddTitle: String = ""
    @State private var hoveredEmptyColumn: String?
    @State private var searchText = ""
    /// Done column collapses to the 5 most-recently-completed; expand shows all.
    @State private var doneExpanded = false
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
    @State private var newTaskColumn: String?
    @State private var composeTemplate: KanbanTemplate?
    /// Sales-pipeline: which stage column's "New Deal" form is open (set by the
    /// `+` button; nil = closed).
    @State private var dealComposeColumn: String?
    /// Bumped every 60s so card header aging tints (orange >6h / red >12h)
    /// advance on a board left open, not just on task events / reloads.
    @State private var agingClock = Date()
    /// Board/Pipeline tab — initialized from project.pipelineMode on appear.
    @State private var viewMode: ViewMode = .board

    // MARK: - "Replay changes" on open
    // When the board opens, briefly show each ticket where it was the LAST time
    // this user looked, then animate it to where collaborators have since moved
    // it — so the diff plays out like pieces sliding across a board. Newly-added
    // tickets get a fading highlight. Board mode only.
    /// taskId → the column to DISPLAY during the replay (its last-seen column).
    /// Empty in steady state — grouping then falls straight through to the
    /// memoized `groupedColumns`, so there's zero per-frame cost when idle.
    @State private var replayOverrides: [String: String] = [:]
    /// taskIds moved or added since this user last looked — outlined in yellow
    /// until the user clicks the card to view its updated state (then removed).
    @State private var changedIds: Set<String> = []
    /// One replay per board mount; set once tasks first load.
    @State private var didReplay = false
    /// Drives matchedGeometryEffect so a card glides from its old column to its
    /// new one when `replayOverrides` clears.
    @Namespace private var cardNS

    private var isPipeline: Bool { viewMode == .pipeline }
    private var pipelineSummary: PipelineSummary { PipelineSummary(tasks: viewModel.tasks) }

    // MARK: - Replay helpers

    // Per-USER, per-project so each collaborator's unread state is isolated even
    // if two accounts share one app install. Changing this key from the old
    // project-only form harmlessly re-baselines once (no false unread flags).
    private func lastSeenKey(_ pid: String) -> String {
        let uid = appState.currentUser?.id ?? "anon"
        return "kanban-lastseen-\(uid)-\(pid)"
    }

    private func loadLastSeen(_ pid: String) -> [String: String] {
        UserDefaults.standard.dictionary(forKey: lastSeenKey(pid)) as? [String: String] ?? [:]
    }
    private func saveLastSeen(_ pid: String, _ map: [String: String]) {
        UserDefaults.standard.set(map, forKey: lastSeenKey(pid))
    }

    /// Tasks to render in `key`, accounting for an active replay. Steady state
    /// (no overrides) returns the memoized column list unchanged — no extra work
    /// on the resize-driven body re-evals the perf fix guards against.
    private func displayTasks(forColumn key: String) -> [MWProjectTask] {
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
        let lastSeen = loadLastSeen(pid)
        // First time this user ever opens the board: establish the baseline
        // silently so nothing is spuriously flagged unread. After that we NEVER
        // re-baseline the whole board — a card only leaves its baseline column
        // when this user actually opens it (see `acknowledge`). That's what makes
        // the yellow ring persist across reloads/relaunches and survive board
        // state changes elsewhere, until the specific collaborator opens the card.
        guard !lastSeen.isEmpty else {
            saveLastSeen(pid, current)
            return
        }

        var overrides: [String: String] = [:]
        for (tid, col) in current {
            if let old = lastSeen[tid], old != col { overrides[tid] = old }   // moved
        }
        let newIds = Set(current.keys.filter { lastSeen[$0] == nil })          // added
        guard !overrides.isEmpty || !newIds.isEmpty else { return }            // unchanged

        replayOverrides = overrides
        // Outline everything that moved or is new in yellow; the ring persists
        // until the user clicks each card to acknowledge its updated state.
        changedIds = Set(overrides.keys).union(newIds)
        Task { @MainActor in
            // Hold the old layout a beat so the eye registers it, then glide.
            try? await Task.sleep(for: .seconds(0.55))
            withAnimation(.spring(response: 0.6, dampingFraction: 0.78)) {
                replayOverrides = [:]
            }
        }
    }

    /// Mark a card as seen by THIS user: drop its yellow ring and advance its
    /// persisted baseline to the current column. This is the ONLY thing that
    /// clears unread — so an untouched card stays highlighted no matter what
    /// state changes happen elsewhere, until this collaborator opens it.
    private func acknowledge(_ taskId: String) {
        if changedIds.contains(taskId) {
            withAnimation(.easeOut(duration: 0.25)) { _ = changedIds.remove(taskId) }
        }
        guard let pid = viewModel.project?.id,
              let task = viewModel.tasks.first(where: { $0.id == taskId }) else { return }
        var baseline = loadLastSeen(pid)
        baseline[taskId] = task.boardColumn
        saveLastSeen(pid, baseline)
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

    var body: some View {
        VStack(spacing: 0) {
            if let err = viewModel.errorMessage {
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
            if viewModel.isLoadingTasks && viewModel.tasks.isEmpty {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else {
                if !viewModel.tasks.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        TextField("Search tasks… (space = AND, \"quotes\" = phrase)", text: $searchText)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText)
                        if !searchText.isEmpty {
                            Button { searchText = "" } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)

                    TaskProgressBar(tasks: viewModel.tasks, compact: true)
                        .padding(.horizontal, 12)
                        .padding(.top, 4)
                        .padding(.bottom, 4)
                }
                if viewModel.project?.projectType == "collab" {
                    boardPipelinePicker
                }
                if isPipeline {
                    pipelineSummaryBar
                } else {
                    AIComposeBar(isDrafting: aiDrafting, error: aiError) { submitAIDraft(prompt: $0) }
                }
                boardColumns
            }
        }
        .background(ThemeRadialBackground())
        .onAppear {
            if viewModel.project?.pipelineMode == true { viewMode = .pipeline }
            TicketUpdatesStore.shared.configure(
                userId: appState.currentUser?.id, projectId: viewModel.project?.id)
            maybeReplay()
            openPendingTaskIfPossible()
        }
        .task {
            if viewModel.tasks.isEmpty {
                await viewModel.loadTasks()
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
        // Re-render once a minute so aging tints advance while the board sits
        // open. Cards carry closures (non-equatable), so the parent re-render
        // re-renders them and recomputes task.aging against the current time.
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { now in
            agingClock = now
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
                        aiError = "Daily AI limit reached (50 per 24 hours). Create tickets manually or try again later."
                    } else {
                        aiError = "Couldn't draft that — try rephrasing."
                    }
                }
            }
        }
    }

    private var headerBar: some View {
        HStack {
            Text("Kanban")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Button { Task { await viewModel.loadTasks() } } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Refresh tasks")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var boardPipelinePicker: some View {
        HStack(spacing: 0) {
            viewModeButton("Board", mode: .board, icon: "square.grid.2x2")
            viewModeButton("Pipeline", mode: .pipeline, icon: "dollarsign.circle")
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.bottom, 4)
    }

    private func viewModeButton(_ label: String, mode: ViewMode, icon: String) -> some View {
        Button {
            viewMode = mode
        } label: {
            HStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 10))
                Text(label).font(.system(size: 11, weight: .medium))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(viewMode == mode ? appState.themeAccent.opacity(0.15) : Color.clear)
            .foregroundColor(viewMode == mode ? appState.themeAccent : .secondary)
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
    }

    /// Below this container width the board stacks columns vertically (scroll
    /// down) instead of horizontally (swipe left/right) — fewer than ~2 columns
    /// fit horizontally in the side-by-side split pane (minWidth 360).
    private let kanbanCompactWidth: CGFloat = 520

    private var boardColumns: some View {
        GeometryReader { geo in
            let compact = geo.size.width < kanbanCompactWidth
            if compact {
                ScrollView(.vertical, showsIndicators: false) {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(columnsFor(mode: viewMode), id: \.key) { col in
                            columnView(key: col.key, label: col.label, compact: true)
                        }
                    }
                    .padding(10)
                }
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 8) {
                        ForEach(columnsFor(mode: viewMode), id: \.key) { col in
                            columnView(key: col.key, label: col.label, compact: false)
                        }
                    }
                    .padding(10)
                }
            }
        }
    }

    /// Sales-pipeline summary bar — open value, weighted forecast, won, count,
    /// win rate. Sits under the search/progress row; pipeline mode only.
    private var pipelineSummaryBar: some View {
        let s = pipelineSummary
        return HStack(spacing: 14) {
            summaryStat("Open", formatDealValue(s.openValue), appState.themeText)
            summaryStat("Forecast", formatDealValue(s.weightedValue), appState.themeAccent)
            summaryStat("Won", formatDealValue(s.wonValue), .green)
            Divider().frame(height: 18)
            summaryStat("Open deals", "\(s.openCount)", appState.themeText.opacity(0.8))
            summaryStat("Win rate", "\(Int((s.winRate * 100).rounded()))%", .green)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func summaryStat(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.system(size: 13, weight: .semibold)).foregroundColor(color)
            Text(label.uppercased())
                .font(.system(size: 8, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.4)
        }
    }

    private func columnView(key: String, label: String, compact: Bool) -> some View {
        // Grouped+sorted once per (tasks, search, mode) in the view model and
        // memoized — a window resize re-evaluates this body every frame, so the
        // filter/sort/date-parse must NOT run here. `orderedTasks` is already in
        // final display order (done column pre-sorted most-recently-completed).
        let orderedTasks = displayTasks(forColumn: key)
        // Done column collapses to the 5 most-recently-completed with a "show
        // more" expander — completed work piles up otherwise.
        let isDoneColumn = !isPipeline && key == "done"
        let doneCollapsed = isDoneColumn && !doneExpanded && orderedTasks.count > 5
        let visibleTasks = doneCollapsed ? Array(orderedTasks.prefix(5)) : orderedTasks
        // Per-stage deal total (pipeline mode only).
        let stageValue = orderedTasks.reduce(0.0) { $0 + ($1.dealValue ?? 0) }
        let isEmpty = orderedTasks.isEmpty
        let isInlineAdding = inlineAddColumn == key
        let isHovered = hoveredEmptyColumn == key
        // Empty columns shrink so populated columns get the breathing room.
        // Hovering or starting an inline-add expands them back to full. Full
        // width is kept tight (240) so all five columns fit without much
        // horizontal scrolling now that there's a Changes Requested lane.
        // In compact (vertical) mode every column is full pane width — no shrink.
        let columnWidth: CGFloat = (isEmpty && !isInlineAdding && !isHovered) ? 100 : 240
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(label.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                Text("\(orderedTasks.count)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(appState.themeText.opacity(0.08))
                    .cornerRadius(4)
                if isPipeline && stageValue > 0 {
                    Text(formatDealValue(stageValue))
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeAccent.opacity(0.12))
                        .cornerRadius(4)
                }
                Spacer()
                if isPipeline {
                    // Sales boards: `+` opens a structured New Deal form
                    // (value/contact/expected-close) so deals are trackable from
                    // creation — not a bare title quick-add.
                    Button {
                        dealComposeColumn = key
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Add deal")
                } else {
                    Menu {
                        Button("Blank task") {
                            inlineAddColumn = key
                            inlineAddTitle = ""
                        }
                        Divider()
                        ForEach(KanbanTemplate.allCases) { tpl in
                            Button {
                                composeTemplate = tpl
                                newTaskColumn = key
                            } label: {
                                Label(tpl.displayName, systemImage: tpl.icon)
                            }
                        }
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()
                    .help("Add task — blank or from a template")
                }
            }
            .padding(.horizontal, 8)
            .padding(.top, 6)

            if isInlineAdding {
                inlineAddRow(column: key)
            }

            // Compact (vertical) mode: render the cards inline so the board's
            // single outer vertical ScrollView owns the scrolling — a nested
            // vertical ScrollView with maxHeight:.infinity would have no
            // intrinsic height inside the outer scroll. Regular mode keeps each
            // column independently scrollable to a filled height.
            if compact {
                columnCards(visibleTasks: visibleTasks, isDoneColumn: isDoneColumn, orderedTasks: orderedTasks)
            } else {
                ScrollView {
                    columnCards(visibleTasks: visibleTasks, isDoneColumn: isDoneColumn, orderedTasks: orderedTasks)
                }
                .frame(maxHeight: .infinity)
            }
        }
        .frame(maxWidth: compact ? .infinity : nil, alignment: .leading)
        .frame(width: compact ? nil : columnWidth)
        .animation(compact ? nil : .easeOut(duration: 0.15), value: columnWidth)
        // Flat tinted fill instead of a glassPanel: each column was an
        // NSVisualEffectView (live blur), and sliding 5 of them horizontally
        // recomposites every frame → the left/right scroll jank. A plain fill
        // over the radial background reads nearly the same and scrolls smooth.
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.cardBackground.opacity(0.40))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.borderColor.opacity(0.5), lineWidth: 1)
        )
        .onHover { hovering in
            // Only react when the column is empty — populated columns don't
            // need to expand.
            if isEmpty {
                hoveredEmptyColumn = hovering ? key : (hoveredEmptyColumn == key ? nil : hoveredEmptyColumn)
            }
        }
        .dropDestination(for: String.self) { items, _ in
            guard let taskId = items.first else { return false }
            Task {
                if viewMode == .pipeline {
                    await viewModel.movePipelineTask(id: taskId, toStage: key)
                } else {
                    await viewModel.moveTask(id: taskId, toColumn: key)
                }
            }
            return true
        }
    }

    /// Card stack for one column — shared by both layouts. Regular mode wraps
    /// this in its own ScrollView; compact (vertical) mode renders it inline
    /// under the board's single outer vertical ScrollView.
    @ViewBuilder
    private func columnCards(visibleTasks: [MWProjectTask], isDoneColumn: Bool, orderedTasks: [MWProjectTask]) -> some View {
        LazyVStack(spacing: 6) {
            ForEach(visibleTasks) { task in
                KanbanCardView(
                    task: task,
                    attachments: viewModel.taskFiles[task.id] ?? [],
                    pipelineMode: isPipeline,
                    elementName: task.elementName
                        ?? viewModel.elements.first(where: { $0.id == task.elementId })?.name,
                    pendingCommitCount: viewModel.pendingSuggestionCount(taskId: task.id),
                    onTap: {
                        // Acknowledge the change → drop the yellow outline and
                        // advance this user's persisted baseline for the card.
                        acknowledge(task.id)
                        viewingTask = task
                    },
                    onToggle: { Task { await viewModel.toggleTaskComplete(id: task.id) } },
                    onMoveColumn: { col in
                        Task {
                            if viewMode == .pipeline {
                                await viewModel.movePipelineTask(id: task.id, toStage: col)
                            } else {
                                await viewModel.moveTask(id: task.id, toColumn: col)
                            }
                        }
                    }
                )
                // Glide across columns when the replay clears its overrides.
                .matchedGeometryEffect(id: task.id, in: cardNS)
                // Yellow ring marks tickets moved/added since the last view;
                // persists until the user clicks the card to acknowledge it.
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .stroke(Color.yellow,
                                lineWidth: changedIds.contains(task.id) ? 2 : 0)
                )
                .draggable(task.id)
                .contextMenu {
                    Button {
                        acknowledge(task.id)
                        viewingTask = task
                    } label: { Label("Open", systemImage: "arrow.up.right.square") }
                    Button {
                        // Reference this ticket into the project chat (reply-style)
                        // and jump to the chat panel so the user can ask about it.
                        appState.pendingTicketRef = TicketChatRef(
                            id: task.id, title: task.title, column: task.boardColumn)
                        appState.pendingProjectPanel = .chat
                    } label: { Label("Chat about this ticket", systemImage: "bubble.left.and.text.bubble.right") }
                    Button(role: .destructive) {
                        taskToDelete = task
                    } label: { Label("Delete", systemImage: "trash") }
                }
            }
            if isDoneColumn && orderedTasks.count > 5 {
                Button {
                    doneExpanded.toggle()
                } label: {
                    Text(doneExpanded ? "Show less" : "Show \(orderedTasks.count - 5) more")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 5)
                        .background(appState.themeText.opacity(0.05))
                        .cornerRadius(5)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 6)
        .padding(.bottom, 8)
    }

    private func inlineAddRow(column: String) -> some View {
        HStack(spacing: 6) {
            TextField("New task", text: $inlineAddTitle)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(5)
                .onSubmit { commitInlineAdd(column: column) }
            Button {
                commitInlineAdd(column: column)
            } label: {
                Image(systemName: "return")
                    .font(.system(size: 9))
                    .foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.return, modifiers: [])
            .disabled(inlineAddTitle.trimmingCharacters(in: .whitespaces).isEmpty)
            Button {
                inlineAddColumn = nil
                inlineAddTitle = ""
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.escape, modifiers: [])
        }
        .padding(.horizontal, 6)
    }

    private func commitInlineAdd(column: String) {
        let trimmed = inlineAddTitle.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        Task {
            if viewMode == .pipeline {
                await viewModel.addTask(title: trimmed, column: "todo", pipelineColumn: column)
            } else {
                await viewModel.addTask(title: trimmed, column: column)
            }
            inlineAddTitle = ""
        }
    }

}
