import SwiftUI
import UniformTypeIdentifiers
import AppKit

private let kanbanColumns: [(key: String, label: String)] = [
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("done", "Done"),
]

private enum ViewMode { case board, pipeline }

private func columnsFor(mode: ViewMode) -> [(key: String, label: String)] {
    mode == .pipeline ? SalesStage.columns : kanbanColumns
}

private func columnsFor(pipeline: Bool) -> [(key: String, label: String)] {
    columnsFor(mode: pipeline ? .pipeline : .board)
}

/// Compact currency for deal values / pipeline totals — "$12k", "$1.2M",
/// "$0" when nil/zero. Pipeline-mode only.
private func formatDealValue(_ value: Double) -> String {
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
    /// Inline-add: which column has its inline TextField visible. Set by the
    /// `+` button on the column header; cleared by Esc / blur / submit.
    @State private var inlineAddColumn: String?
    @State private var inlineAddTitle: String = ""
    @State private var hoveredEmptyColumn: String?
    @State private var searchText = ""
    /// Done column collapses to the 5 most-recently-completed; expand shows all.
    @State private var doneExpanded = false
    /// Template-compose sheet. `newTaskColumn` is the destination column;
    /// `composeTemplate` the picked template (scaffold + default priority +
    /// category). Reuses the single legacy sheet slot to avoid a 4th `.sheet`.
    @State private var newTaskColumn: String?
    @State private var composeTemplate: KanbanTemplate?
    /// Bumped every 60s so card header aging tints (orange >6h / red >12h)
    /// advance on a board left open, not just on task events / reloads.
    @State private var agingClock = Date()
    /// Board/Pipeline tab — initialized from project.pipelineMode on appear.
    @State private var viewMode: ViewMode = .board

    private var isPipeline: Bool { viewMode == .pipeline }
    private var pipelineSummary: PipelineSummary { PipelineSummary(tasks: viewModel.tasks) }

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
                }
                boardColumns
            }
        }
        .background(ThemeRadialBackground())
        .onAppear {
            if viewModel.project?.pipelineMode == true { viewMode = .pipeline }
        }
        .task {
            if viewModel.tasks.isEmpty {
                await viewModel.loadTasks()
            }
        }
        // Re-render once a minute so aging tints advance while the board sits
        // open. Cards carry closures (non-equatable), so the parent re-render
        // re-renders them and recomputes task.aging against the current time.
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { now in
            agingClock = now
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

    private var boardColumns: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(columnsFor(mode: viewMode), id: \.key) { col in
                    columnView(key: col.key, label: col.label)
                }
            }
            .padding(10)
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

    private func columnView(key: String, label: String) -> some View {
        let cols = columnsFor(mode: viewMode)
        let colKeys = Set(cols.map { $0.key })
        let isFirstColumn = cols.first?.key == key
        let colTasks = viewModel.tasks
            .filter { task in
                let taskCol = viewMode == .pipeline
                    ? (task.pipelineColumn ?? "lead")
                    : task.boardColumn
                return taskCol == key || (isFirstColumn && !colKeys.contains(taskCol))
            }
            .filter { taskMatchesSearch($0) }
            .sorted {
                // Seriousness dictates order: critical → high → medium → low.
                // Secondary: oldest-waiting first within a priority bucket, so
                // the longest-pending (and reddest) card floats to the top.
                if $0.priorityRank != $1.priorityRank { return $0.priorityRank < $1.priorityRank }
                return (PacificDateFormatter.parse($0.createdAt) ?? .distantFuture)
                     < (PacificDateFormatter.parse($1.createdAt) ?? .distantFuture)
            }
        // Done column collapses to the 5 most-recently-completed (newest first)
        // with a "show more" expander — completed work piles up otherwise.
        let isDoneColumn = !isPipeline && key == "done"
        let orderedTasks: [MWProjectTask] = isDoneColumn
            ? colTasks.sorted {
                (PacificDateFormatter.parse($0.completedAt ?? $0.updatedAt ?? $0.createdAt) ?? .distantPast)
                > (PacificDateFormatter.parse($1.completedAt ?? $1.updatedAt ?? $1.createdAt) ?? .distantPast)
              }
            : colTasks
        let doneCollapsed = isDoneColumn && !doneExpanded && orderedTasks.count > 5
        let visibleTasks = doneCollapsed ? Array(orderedTasks.prefix(5)) : orderedTasks
        // Per-stage deal total (pipeline mode only).
        let stageValue = colTasks.reduce(0.0) { $0 + ($1.dealValue ?? 0) }
        let isEmpty = colTasks.isEmpty
        let isInlineAdding = inlineAddColumn == key
        let isHovered = hoveredEmptyColumn == key
        // Empty columns shrink to ~110px so populated columns get the breathing
        // room. Hovering or starting an inline-add expands them back to full.
        let columnWidth: CGFloat = (isEmpty && !isInlineAdding && !isHovered) ? 110 : 300
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(label.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                Text("\(colTasks.count)")
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
                    // Sales boards: a deal is just a titled card; details are
                    // filled in the editor. Skip the engineering/bug template
                    // menu, which is meaningless for a pipeline.
                    Button {
                        inlineAddColumn = key
                        inlineAddTitle = ""
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

            ScrollView {
                LazyVStack(spacing: 6) {
                    ForEach(visibleTasks) { task in
                        KanbanCardView(
                            task: task,
                            attachments: viewModel.taskFiles[task.id] ?? [],
                            pipelineMode: isPipeline,
                            elementName: task.elementName
                                ?? viewModel.elements.first(where: { $0.id == task.elementId })?.name,
                            onTap: { viewingTask = task },
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
                        .draggable(task.id)
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
            .frame(maxHeight: .infinity)
        }
        .frame(width: columnWidth)
        .animation(.easeOut(duration: 0.15), value: columnWidth)
        .glassPanel(cornerRadius: 8, material: .underWindowBackground,
                    tint: Color.cardBackground, tintOpacity: 0.40,
                    stroke: Color.borderColor.opacity(0.5), shadow: false)
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

    // MARK: - Search

    private func taskMatchesSearch(_ task: MWProjectTask) -> Bool {
        guard !searchText.isEmpty else { return true }
        let tokens = parseSearchTokens(searchText)
        guard !tokens.isEmpty else { return true }
        let haystack = [
            task.title,
            task.description ?? "",
            task.progressNote ?? "",
            task.displayAssignee ?? "",
            task.priority,
            task.category ?? "",
            task.boardColumn,
        ].joined(separator: " ").lowercased()
        return tokens.allSatisfy { haystack.contains($0.lowercased()) }
    }

    /// Splits a query into tokens. Quoted substrings (e.g. `"login page"`) are
    /// treated as a single phrase token; unquoted space-separated words are
    /// individual AND terms.
    private func parseSearchTokens(_ query: String) -> [String] {
        var tokens: [String] = []
        var current = ""
        var inQuotes = false
        for ch in query {
            switch ch {
            case "\"":
                if inQuotes {
                    if !current.isEmpty { tokens.append(current); current = "" }
                    inQuotes = false
                } else {
                    inQuotes = true
                }
            case " " where !inQuotes:
                if !current.isEmpty { tokens.append(current); current = "" }
            default:
                current.append(ch)
            }
        }
        if !current.isEmpty { tokens.append(current) }
        return tokens.filter { !$0.isEmpty }
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

/// Create-mode sheet for template-based tickets. Distinct from the edit-only
/// `TaskEditorSheet` (whose `task` is non-optional and whose upload UI needs an
/// existing task id). Prefills the description scaffold + default priority +
/// category, then creates on Add.
private struct TaskComposeContent: View {
    @Environment(AppState.self) private var appState
    let column: String
    let template: KanbanTemplate
    @Bindable var viewModel: ProjectDetailViewModel
    let onClose: () -> Void

    @State private var title: String = ""
    /// One entry per `template.fields` element, keyed by field.key. Composed
    /// into the markdown description on Add.
    @State private var fieldValues: [String: String] = [:]
    @State private var priority: String
    @State private var assignedTo: String?
    @State private var selectedElementId: String?
    @State private var isAddingElement = false
    @State private var newElementName = ""

    init(column: String, template: KanbanTemplate, viewModel: ProjectDetailViewModel, onClose: @escaping () -> Void) {
        self.column = column
        self.template = template
        self.viewModel = viewModel
        self.onClose = onClose
        _priority = State(initialValue: template.defaultPriority)
    }

    private func fieldBinding(_ key: String) -> Binding<String> {
        Binding(get: { fieldValues[key] ?? "" }, set: { fieldValues[key] = $0 })
    }

    private let priorities: [(key: String, label: String)] = [
        ("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: template.icon)
                    .font(.system(size: 12))
                    .foregroundColor(template.color)
                Text("New \(template.displayName) Ticket")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
            }

            TextField("Title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText)
                .padding(8)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(6)

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(template.fields) { field in
                        fieldEditor(for: field)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(maxHeight: 300)

            HStack(spacing: 6) {
                Text("Priority")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Picker("", selection: $priority) {
                    ForEach(priorities, id: \.key) { p in
                        Text(p.label).tag(p.key)
                    }
                }
                .labelsHidden()
                .fixedSize()
                Spacer()
            }

            elementPickerRow

            if !viewModel.collaborators.isEmpty {
                HStack(spacing: 6) {
                    Text("Assignee")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Picker("", selection: $assignedTo) {
                        Text("Unassigned").tag(String?.none)
                        ForEach(viewModel.collaborators) { c in
                            Text(c.name).tag(String?.some(c.userId))
                        }
                    }
                    .labelsHidden()
                    .fixedSize()
                    Spacer()
                }
            }

            HStack {
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add") {
                    let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !t.isEmpty else { return }
                    let desc = KanbanTemplate.composeDescription(
                        fields: template.fields, values: fieldValues
                    )
                    Task {
                        await viewModel.addTask(
                            title: t, column: column, priority: priority,
                            assignedTo: assignedTo,
                            description: desc.isEmpty ? nil : desc,
                            category: template.rawValue,
                            elementId: selectedElementId
                        )
                        onClose()
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(.matcha500)
                .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 420)
        .glassPanel(cornerRadius: 0, material: .hudWindow, blending: .behindWindow,
                    tint: Color.appBackground, tintOpacity: 0.62, shadow: false)
    }

    /// Renders one structured field (labeled). Single-line → TextField,
    /// multi-line → TextEditor with a placeholder overlay (TextEditor has no
    /// native placeholder), picker → segmented dropdown with an empty "—" tag.
    @ViewBuilder
    private func fieldEditor(for field: KanbanTemplate.TicketField) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(field.label.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            switch field.kind {
            case .singleLine:
                TextField(field.placeholder, text: fieldBinding(field.key))
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .padding(7)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(5)
            case .multiLine:
                TextEditor(text: fieldBinding(field.key))
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.9))
                    .scrollContentBackground(.hidden)
                    .padding(5)
                    .frame(height: 60)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(5)
                    .overlay(alignment: .topLeading) {
                        if (fieldValues[field.key] ?? "").isEmpty && !field.placeholder.isEmpty {
                            Text(field.placeholder)
                                .font(.system(size: 12))
                                .foregroundColor(.secondary.opacity(0.55))
                                .padding(.horizontal, 9)
                                .padding(.top, 11)
                                .allowsHitTesting(false)
                        }
                    }
            case .picker(let options):
                Picker("", selection: fieldBinding(field.key)) {
                    Text("—").tag("")
                    ForEach(options, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .fixedSize()
            }
        }
    }

    /// Element row: pick an existing element or create one inline via "＋ New".
    /// Extracted to keep the compose body within the SwiftUI type-check budget.
    @ViewBuilder
    private var elementPickerRow: some View {
        HStack(spacing: 6) {
            Text("Element")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            if isAddingElement {
                TextField("New element name", text: $newElementName)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .padding(6)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(5)
                    .frame(maxWidth: 180)
                    .onSubmit { commitNewElement() }
                Button("Add") { commitNewElement() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                    .disabled(newElementName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Cancel") { isAddingElement = false; newElementName = "" }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                Picker("", selection: $selectedElementId) {
                    Text("None").tag(String?.none)
                    ForEach(viewModel.elements) { el in
                        Text(el.name).tag(String?.some(el.id))
                    }
                }
                .labelsHidden()
                .fixedSize()
                Button {
                    isAddingElement = true
                    newElementName = ""
                } label: {
                    HStack(spacing: 2) {
                        Image(systemName: "plus").font(.system(size: 9))
                        Text("New").font(.system(size: 11))
                    }
                    .foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
    }

    private func commitNewElement() {
        let n = newElementName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        Task {
            if let el = await viewModel.createElement(name: n, kind: nil, description: nil, assignedTo: nil) {
                await MainActor.run {
                    selectedElementId = el.id
                    isAddingElement = false
                    newElementName = ""
                }
            }
        }
    }
}

private struct KanbanCardView: View {
    @Environment(AppState.self) private var appState
    let task: MWProjectTask
    let attachments: [MWProjectFile]
    var pipelineMode: Bool = false
    /// Element label resolved by the board (task.elementName from the list
    /// query, with a client-side fallback so freshly created/edited cards show
    /// it before the next full reload).
    var elementName: String? = nil
    let onTap: () -> Void
    let onToggle: () -> Void
    let onMoveColumn: (String) -> Void

    /// "Company · Contact" for the card face (pipeline mode); nil when neither set.
    private var contactDisplay: String? {
        let parts = [task.contactCompany, task.contactName]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var imageAttachments: [MWProjectFile] { attachments.filter { $0.isImage } }
    private var nonImageCount: Int { attachments.count - imageAttachments.count }

    private var priorityColor: Color {
        switch task.priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .secondary
        }
    }

    private var currentColumnLabel: String {
        columnsFor(pipeline: pipelineMode).first(where: { $0.key == task.boardColumn })?.label ?? task.boardColumn
    }

    private var assigneeDisplay: String? { task.displayAssignee }

    private var assigneeInitial: String? {
        guard let name = assigneeDisplay, !name.isEmpty else { return nil }
        return String(name.prefix(1)).uppercased()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header band — checkbox + title. Tints orange after 6h / red after
            // 12h of inactivity (anchor = lastMovedAt ?? createdAt); never for
            // done/completed cards. See MWProjectTask.aging.
            HStack(alignment: .top, spacing: 8) {
                // Pipeline deals use the Won/Lost outcome, not task completion —
                // the checkbox would shove the card into 'done' (an orphan stage
                // here). Hide it in pipeline mode.
                if !pipelineMode {
                    Button(action: onToggle) {
                        Image(systemName: task.status == "completed" ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 13))
                            .foregroundColor(task.status == "completed" ? .matcha500 : .secondary)
                    }
                    .buttonStyle(.plain)
                }

                Text(task.title)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .strikethrough(task.status == "completed")
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(8)
            .background(headerTint)

            VStack(alignment: .leading, spacing: 3) {
                if let note = task.progressNote, !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "location.north.line")
                            .font(.system(size: 8))
                            .foregroundColor(appState.themeAccent)
                        Text(note)
                            .font(.system(size: 10))
                            .italic()
                            .foregroundColor(appState.themeText.opacity(0.6))
                            .lineLimit(1)
                    }
                }

                if pipelineMode, let contact = contactDisplay {
                    HStack(spacing: 4) {
                        Image(systemName: "building.2")
                            .font(.system(size: 8))
                            .foregroundColor(.secondary)
                        Text(contact)
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.7))
                            .lineLimit(1)
                    }
                }

                HStack(spacing: 5) {
                    Circle().fill(priorityColor).frame(width: 5, height: 5)

                    if pipelineMode {
                        if let dv = task.dealValue, dv > 0 {
                            Text(formatDealValue(dv))
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(appState.themeAccent)
                        }
                        if task.dealOutcome != "open" {
                            Text(task.dealOutcome.capitalized)
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(task.dealOutcome == "won" ? .green : .red)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background((task.dealOutcome == "won" ? Color.green : Color.red).opacity(0.15))
                                .cornerRadius(3)
                        }
                    }

                    if let tpl = KanbanTemplate.from(category: task.category) {
                        HStack(spacing: 2) {
                            Image(systemName: tpl.icon).font(.system(size: 7))
                            Text(tpl.displayName).font(.system(size: 8, weight: .semibold))
                        }
                        .foregroundColor(tpl.color)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(tpl.color.opacity(0.15))
                        .cornerRadius(3)
                    }

                    if let elName = elementName ?? task.elementName {
                        HStack(spacing: 2) {
                            Image(systemName: "square.stack.3d.up.fill").font(.system(size: 7))
                            Text(elName).font(.system(size: 8, weight: .medium))
                        }
                        .foregroundColor(appState.themeAccent)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(appState.themeAccent.opacity(0.12))
                        .cornerRadius(3)
                    }

                    Menu {
                        ForEach(columnsFor(pipeline: pipelineMode), id: \.key) { c in
                            Button {
                                if c.key != task.boardColumn { onMoveColumn(c.key) }
                            } label: {
                                if c.key == task.boardColumn {
                                    Label(c.label, systemImage: "checkmark")
                                } else {
                                    Text(c.label)
                                }
                            }
                        }
                    } label: {
                        Text(currentColumnLabel)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(appState.themeText.opacity(0.8))
                            .tracking(0.3)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(appState.themeText.opacity(0.08))
                            .cornerRadius(8)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()

                    if let initial = assigneeInitial, let name = assigneeDisplay {
                        Circle()
                            .fill(appState.themeAccent.opacity(0.18))
                            .frame(width: 14, height: 14)
                            .overlay(
                                Text(initial)
                                    .font(.system(size: 8, weight: .semibold))
                                    .foregroundColor(appState.themeAccent)
                            )
                        Text(name)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                    }

                    if let due = task.dueDate, !due.isEmpty {
                        Image(systemName: "calendar")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                        Text(due.prefix(10))
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }

                timestampLine

                if !attachments.isEmpty {
                    attachmentStrip
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 8)
            .padding(.bottom, 8)
            .padding(.top, 4)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .elevatedCard(cornerRadius: 8)
        .onTapGesture(perform: onTap)
    }

    /// Header background tint by inactivity age. Clear when fresh / done.
    private var headerTint: Color {
        switch task.aging {
        case .none: return .clear
        case .warn: return .orange.opacity(0.18)
        case .overdue: return .red.opacity(0.18)
        }
    }

    /// "Added <date> at <time> · Moved <relative>" in Pacific time. The exact
    /// creation time makes wait-duration legible. Moved only shows once the
    /// card has crossed columns at least once (lastMovedAt != nil).
    @ViewBuilder
    private var timestampLine: some View {
        if let added = PacificDateFormatter.dateTime(task.createdAt) {
            HStack(spacing: 3) {
                Text("Added \(added)")
                if let moved = PacificDateFormatter.relative(task.lastMovedAt) {
                    Text("· Moved \(moved)")
                }
            }
            .font(.system(size: 9))
            .foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    private var attachmentStrip: some View {
        if imageAttachments.isEmpty {
            HStack(spacing: 4) {
                Image(systemName: "paperclip")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                Text("\(attachments.count)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        } else {
            HStack(spacing: 4) {
                ForEach(imageAttachments.prefix(3)) { f in
                    AsyncImage(url: URL(string: f.storageUrl)) { phase in
                        switch phase {
                        case .success(let img):
                            img.resizable().aspectRatio(contentMode: .fill)
                        default:
                            Rectangle().fill(Color.white.opacity(0.08))
                        }
                    }
                    .frame(width: 24, height: 24)
                    .clipShape(RoundedRectangle(cornerRadius: 3))
                }
                let extras = (imageAttachments.count - 3) + nonImageCount
                if extras > 0 {
                    Text("+\(extras)")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.white.opacity(0.08))
                        .cornerRadius(3)
                }
            }
        }
    }
}

private struct TaskEditorSheet: View {
    let task: MWProjectTask
    @Bindable var viewModel: ProjectDetailViewModel
    let onSave: (MatchaWorkService.ProjectTaskPatch) -> Void
    let onDelete: () -> Void
    let onClose: () -> Void

    @State private var title: String
    @State private var description: String
    @State private var priority: String
    @State private var dueDate: String
    @State private var boardColumn: String
    @State private var pipelineColumn: String
    @State private var progressNote: String
    @State private var assignedTo: String?
    @State private var selectedElementId: String?
    @State private var isAddingElement = false
    @State private var newElementName = ""
    @State private var uploadingName: String?
    @State private var isDragOverAttachments = false
    /// Local state. The attachment preview presents nested over this editor
    /// sheet — hoisting it out causes sibling-sheet conflict (only one
    /// `.sheet` per view on macOS) and the preview never shows until the
    /// editor dismisses.
    @State private var previewFile: MWProjectFile?

    // ── Sales-pipeline editor state (surfaced only when project.pipelineMode) ──
    @State private var dealValue: String
    @State private var probability: String
    @State private var contactName: String
    @State private var contactCompany: String
    @State private var contactEmail: String
    @State private var contactPhone: String
    @State private var outcome: String
    @State private var lossReason: String
    @State private var nextActionAt: String
    @State private var expectedClose: String
    @State private var activityNote: String = ""

    init(
        task: MWProjectTask,
        viewModel: ProjectDetailViewModel,
        onSave: @escaping (MatchaWorkService.ProjectTaskPatch) -> Void,
        onDelete: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.task = task
        self.viewModel = viewModel
        self.onSave = onSave
        self.onDelete = onDelete
        self.onClose = onClose
        _title = State(initialValue: task.title)
        _description = State(initialValue: task.description ?? "")
        _priority = State(initialValue: task.priority)
        _dueDate = State(initialValue: task.dueDate.map { String($0.prefix(10)) } ?? "")
        _boardColumn = State(initialValue: task.boardColumn)
        _pipelineColumn = State(initialValue: task.pipelineColumn ?? "lead")
        _progressNote = State(initialValue: task.progressNote ?? "")
        _assignedTo = State(initialValue: task.assignedTo)
        _selectedElementId = State(initialValue: task.elementId)
        _dealValue = State(initialValue: task.dealValue.map { String(format: "%g", $0) } ?? "")
        _probability = State(initialValue: task.probability.map(String.init) ?? "")
        _contactName = State(initialValue: task.contactName ?? "")
        _contactCompany = State(initialValue: task.contactCompany ?? "")
        _contactEmail = State(initialValue: task.contactEmail ?? "")
        _contactPhone = State(initialValue: task.contactPhone ?? "")
        _outcome = State(initialValue: task.dealOutcome)
        _lossReason = State(initialValue: task.lossReason ?? "")
        _nextActionAt = State(initialValue: task.nextActionAt.map { String($0.prefix(10)) } ?? "")
        _expectedClose = State(initialValue: task.expectedClose.map { String($0.prefix(10)) } ?? "")
    }

    private var collaborators: [MWProjectCollaborator] { viewModel.collaborators }
    private var attachments: [MWProjectFile] { viewModel.taskFiles[task.id] ?? [] }
    /// Show pipeline/deal fields for all collab projects — both views are available.
    private var isPipeline: Bool { viewModel.project?.projectType == "collab" }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Edit Task")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            TextField("Title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 4) {
                    Image(systemName: "location.north.line")
                        .font(.system(size: 9))
                        .foregroundColor(.matcha500)
                    Text("WHERE WE'RE AT")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.matcha500)
                        .tracking(0.5)
                }
                TextField("Current status, blockers, latest update…", text: $progressNote, axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .lineLimit(2...5)
                    .padding(8)
                    .background(Color.zinc800)
                    .cornerRadius(6)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .strokeBorder(Color.matcha500.opacity(0.4), lineWidth: 1)
                    )
            }

            TextField("Description", text: $description, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .lineLimit(2...6)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)

            HStack(spacing: 8) {
                Picker("Column", selection: $boardColumn) {
                    ForEach(kanbanColumns, id: \.key) { c in Text(c.label).tag(c.key) }
                }
                .pickerStyle(.menu)
                if isPipeline {
                    Picker("Stage", selection: $pipelineColumn) {
                        ForEach(SalesStage.columns, id: \.key) { c in Text(c.label).tag(c.key) }
                    }
                    .pickerStyle(.menu)
                }
                Picker("Priority", selection: $priority) {
                    Text("Critical").tag("critical")
                    Text("High").tag("high")
                    Text("Medium").tag("medium")
                    Text("Low").tag("low")
                }
                .pickerStyle(.menu)
            }

            if isPipeline {
                salesSection
            }

            elementEditorRow

            Picker("Assignee", selection: $assignedTo) {
                Text("Unassigned").tag(Optional<String>.none)
                ForEach(collaborators) { c in
                    Text(c.name).tag(Optional(c.userId))
                }
            }
            .pickerStyle(.menu)

            TextField("Due date (YYYY-MM-DD, optional)", text: $dueDate)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)

            attachmentsSection

            HStack {
                Button {
                    onDelete()
                } label: {
                    Text("Delete")
                        .font(.system(size: 12))
                        .foregroundColor(.red)
                }
                .buttonStyle(.plain)

                Spacer()

                Button("Save") {
                    // assigned_to: send UUID to assign, empty string to clear
                    // (backend `UUID(v) if v else None` nulls falsy). nil would
                    // skip the field entirely via encodeIfPresent.
                    let assigneeWire: String = assignedTo ?? ""
                    let patch = MatchaWorkService.ProjectTaskPatch(
                        title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                        description: description,
                        boardColumn: boardColumn,
                        pipelineColumn: isPipeline ? pipelineColumn : nil,
                        priority: priority,
                        dueDate: dueDate.isEmpty ? nil : dueDate,
                        assignedTo: assigneeWire,
                        progressNote: progressNote,
                        elementId: selectedElementId ?? "",
                        // Sales fields only for collab projects; nil = omitted.
                        dealValue: isPipeline ? Double(dealValue) : nil,
                        probability: isPipeline ? Int(probability) : nil,
                        contactName: isPipeline ? contactName : nil,
                        contactCompany: isPipeline ? contactCompany : nil,
                        contactEmail: isPipeline ? contactEmail : nil,
                        contactPhone: isPipeline ? contactPhone : nil,
                        outcome: isPipeline ? outcome : nil,
                        lossReason: isPipeline ? lossReason : nil,
                        nextActionAt: isPipeline ? nextActionAt : nil,
                        expectedClose: isPipeline ? expectedClose : nil
                    )
                    onSave(patch)
                }
                .buttonStyle(.plain)
                .foregroundColor(.matcha500)
            }
        }
        .padding(16)
        .frame(width: 420)
        .background(Color.appBackground)
        .task {
            if viewModel.taskFiles[task.id] == nil {
                await viewModel.loadTaskFiles(taskId: task.id)
            }
        }
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
    }

    /// Element row: pick an existing element or create one inline via "＋ New".
    @ViewBuilder
    private var elementEditorRow: some View {
        if isAddingElement {
            HStack(spacing: 6) {
                Text("Element").font(.system(size: 11)).foregroundColor(.secondary)
                TextField("New element name", text: $newElementName)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .padding(6)
                    .background(Color.zinc800)
                    .cornerRadius(5)
                    .onSubmit { commitNewElement() }
                Button("Add") { commitNewElement() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                    .disabled(newElementName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Cancel") { isAddingElement = false; newElementName = "" }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        } else {
            HStack(spacing: 6) {
                Picker("Element", selection: $selectedElementId) {
                    Text("No element").tag(Optional<String>.none)
                    ForEach(viewModel.elements) { el in
                        Text(el.name).tag(Optional(el.id))
                    }
                }
                .pickerStyle(.menu)
                Button {
                    isAddingElement = true
                    newElementName = ""
                } label: {
                    HStack(spacing: 2) {
                        Image(systemName: "plus").font(.system(size: 9))
                        Text("New").font(.system(size: 11))
                    }
                    .foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func commitNewElement() {
        let n = newElementName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        Task {
            if let el = await viewModel.createElement(name: n, kind: nil, description: nil, assignedTo: nil) {
                await MainActor.run {
                    selectedElementId = el.id
                    isAddingElement = false
                    newElementName = ""
                }
            }
        }
    }

    /// Deal / Outcome / Follow-up fields for a sales pipeline. Hardcoded-dark
    /// to match the rest of this editor (see werk-theme-conventions — this
    /// sheet is the deferred-from-theming one).
    @ViewBuilder
    private var salesSection: some View {
        // Grouped into three sub-stacks to stay within the ViewBuilder
        // 10-child limit and keep each section's type-check cheap.
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 8) {
                sectionLabel("DEAL")
                HStack(spacing: 8) {
                    darkField("Value ($)", text: $dealValue)
                    darkField("Win %", text: $probability)
                }
                HStack(spacing: 8) {
                    darkField("Company", text: $contactCompany)
                    darkField("Contact", text: $contactName)
                }
                HStack(spacing: 8) {
                    darkField("Email", text: $contactEmail)
                    darkField("Phone", text: $contactPhone)
                }
                darkField("Expected close (YYYY-MM-DD)", text: $expectedClose)
            }
            VStack(alignment: .leading, spacing: 8) {
                sectionLabel("OUTCOME")
                Picker("", selection: $outcome) {
                    Text("Open").tag("open")
                    Text("Won").tag("won")
                    Text("Lost").tag("lost")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                if outcome == "lost" {
                    darkField("Loss reason", text: $lossReason)
                }
            }
            VStack(alignment: .leading, spacing: 8) {
                sectionLabel("FOLLOW-UP")
                darkField("Next action (YYYY-MM-DD)", text: $nextActionAt)
                activityLogRow
            }
        }
    }

    private var activityLogRow: some View {
        HStack(spacing: 6) {
            TextField("Log a call / email / note…", text: $activityNote)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)
            Menu {
                ForEach(["call", "email", "note", "meeting"], id: \.self) { kind in
                    Button(kind.capitalized) { logActivity(kind) }
                }
            } label: {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 16))
                    .foregroundColor(.matcha500)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Log a follow-up activity")
        }
    }

    private func sectionLabel(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(.matcha500)
            .tracking(0.5)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func darkField(_ placeholder: String, text: Binding<String>) -> some View {
        TextField(placeholder, text: text)
            .textFieldStyle(.plain)
            .font(.system(size: 12))
            .foregroundColor(.white)
            .padding(8)
            .background(Color.zinc800)
            .cornerRadius(6)
    }

    /// Log a follow-up activity onto the task history timeline, then clear the
    /// note field. Best-effort; failures are silent (the timeline reload will
    /// simply not show it).
    private func logActivity(_ kind: String) {
        let note = activityNote.trimmingCharacters(in: .whitespacesAndNewlines)
        let pid = task.projectId ?? viewModel.project?.id ?? ""
        guard !pid.isEmpty else { return }
        Task {
            try? await MatchaWorkService.shared.logTaskActivity(
                projectId: pid, taskId: task.id, kind: kind,
                body: note.isEmpty ? nil : note
            )
            await MainActor.run { activityNote = "" }
        }
    }

    @ViewBuilder
    private var attachmentsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "paperclip")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("ATTACHMENTS")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if !attachments.isEmpty {
                    Text("\(attachments.count)")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
                Spacer()
                if let name = uploadingName {
                    Text("Uploading \(name)…")
                        .font(.system(size: 10))
                        .foregroundColor(.matcha500)
                        .lineLimit(1)
                } else {
                    Button("Add") { browseForAttachment() }
                        .buttonStyle(.plain)
                        .font(.system(size: 10))
                        .foregroundColor(.matcha500)
                }
            }

            if attachments.isEmpty {
                HStack {
                    Image(systemName: "square.and.arrow.up")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Text("Drop files here or click Add")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 10)
                .background(isDragOverAttachments ? Color.matcha500.opacity(0.08) : Color.zinc800.opacity(0.4))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(isDragOverAttachments ? Color.matcha500 : Color.white.opacity(0.1),
                                style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                )
                .cornerRadius(6)
            } else {
                VStack(spacing: 3) {
                    ForEach(attachments) { f in
                        AttachmentRow(file: f) {
                            openAttachment(f)
                        } onDelete: {
                            Task { await viewModel.deleteTaskFile(taskId: task.id, fileId: f.id) }
                        }
                    }
                }
            }
        }
        .onDrop(of: [.fileURL], isTargeted: $isDragOverAttachments) { providers in
            handleAttachmentDrop(providers)
            return true
        }
    }

    private func openAttachment(_ file: MWProjectFile) {
        previewFile = file
    }

    private func browseForAttachment() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.begin { response in
            guard response == .OK else { return }
            for url in panel.urls {
                uploadURL(url)
            }
        }
    }

    private func handleAttachmentDrop(_ providers: [NSItemProvider]) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                Task { @MainActor in uploadURL(url) }
            }
        }
    }

    private func uploadURL(_ url: URL) {
        guard let data = try? Data(contentsOf: url) else { return }
        let ext = url.pathExtension.lowercased()
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
        let name = url.lastPathComponent
        Task { @MainActor in uploadingName = name }
        Task {
            await viewModel.uploadTaskFile(
                taskId: task.id, data: data, filename: name, mimeType: mime
            )
            await MainActor.run { uploadingName = nil }
        }
    }
}

private struct AttachmentRow: View {
    let file: MWProjectFile
    let onOpen: () -> Void
    let onDelete: () -> Void
    @State private var isHovered = false

    private var sizeLabel: String {
        let bytes = Double(file.fileSize)
        if bytes < 1024 { return "\(file.fileSize) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / 1024 / 1024)
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: file.isImage ? "photo" : "doc")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            Text(file.filename)
                .font(.system(size: 11))
                .foregroundColor(.white)
                .lineLimit(1)
            Text(sizeLabel)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            Spacer()
            if isHovered {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 10))
                        .foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("Delete")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(isHovered ? Color.zinc800 : Color.zinc800.opacity(0.5))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture(perform: onOpen)
    }
}
