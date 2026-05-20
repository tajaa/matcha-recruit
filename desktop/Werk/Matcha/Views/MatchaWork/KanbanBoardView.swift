import SwiftUI
import UniformTypeIdentifiers
import AppKit

private let kanbanColumns: [(key: String, label: String)] = [
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("done", "Done"),
]

struct KanbanBoardView: View {
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
    /// Template-compose sheet. `newTaskColumn` is the destination column;
    /// `composeTemplate` the picked template (scaffold + default priority +
    /// category). Reuses the single legacy sheet slot to avoid a 4th `.sheet`.
    @State private var newTaskColumn: String?
    @State private var composeTemplate: KanbanTemplate?

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
                    TaskProgressBar(tasks: viewModel.tasks, compact: true)
                        .padding(.horizontal, 12)
                        .padding(.top, 8)
                        .padding(.bottom, 4)
                }
                boardColumns
            }
        }
        .background(Color.appBackground)
        // Only fetch when we have nothing yet. The eager prefetch in
        // `loadProject` already runs for collab projects, and a background
        // refresh races user toggles: a stale GET-list response can land
        // after the PATCH and overwrite the optimistic done-state with
        // the pre-toggle todo state, snapping the card back across columns.
        .task {
            if viewModel.tasks.isEmpty {
                await viewModel.loadTasks()
            }
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

    private var boardColumns: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(kanbanColumns, id: \.key) { col in
                    columnView(key: col.key, label: col.label)
                }
            }
            .padding(10)
        }
    }

    private func columnView(key: String, label: String) -> some View {
        let colTasks = viewModel.tasks.filter { $0.boardColumn == key }
        let isEmpty = colTasks.isEmpty
        let isInlineAdding = inlineAddColumn == key
        let isHovered = hoveredEmptyColumn == key
        // Empty columns shrink to ~110px so populated columns get the breathing
        // room. Hovering or starting an inline-add expands them back to 220px.
        let columnWidth: CGFloat = (isEmpty && !isInlineAdding && !isHovered) ? 110 : 220
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
                    .background(Color.zinc800)
                    .cornerRadius(4)
                Spacer()
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
            .padding(.horizontal, 8)
            .padding(.top, 6)

            if isInlineAdding {
                inlineAddRow(column: key)
            }

            ScrollView {
                LazyVStack(spacing: 6) {
                    ForEach(colTasks) { task in
                        KanbanCardView(
                            task: task,
                            attachments: viewModel.taskFiles[task.id] ?? [],
                            onTap: { viewingTask = task },
                            onToggle: { Task { await viewModel.toggleTaskComplete(id: task.id) } },
                            onMoveColumn: { col in Task { await viewModel.moveTask(id: task.id, toColumn: col) } }
                        )
                        .draggable(task.id)
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
            Task { await viewModel.moveTask(id: taskId, toColumn: key) }
            return true
        }
    }

    private func inlineAddRow(column: String) -> some View {
        HStack(spacing: 6) {
            TextField("New task", text: $inlineAddTitle)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color.zinc800)
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
            await viewModel.addTask(title: trimmed, column: column)
            inlineAddTitle = ""
            // Keep the row open so the user can keep jotting; Esc to dismiss.
        }
    }

}

/// Create-mode sheet for template-based tickets. Distinct from the edit-only
/// `TaskEditorSheet` (whose `task` is non-optional and whose upload UI needs an
/// existing task id). Prefills the description scaffold + default priority +
/// category, then creates on Add.
private struct TaskComposeContent: View {
    let column: String
    let template: KanbanTemplate
    @Bindable var viewModel: ProjectDetailViewModel
    let onClose: () -> Void

    @State private var title: String = ""
    @State private var description: String
    @State private var priority: String

    init(column: String, template: KanbanTemplate, viewModel: ProjectDetailViewModel, onClose: @escaping () -> Void) {
        self.column = column
        self.template = template
        self.viewModel = viewModel
        self.onClose = onClose
        _description = State(initialValue: template.scaffold)
        _priority = State(initialValue: template.defaultPriority)
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
                    .foregroundColor(.white)
            }

            TextField("Title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)

            TextEditor(text: $description)
                .font(.system(size: 12))
                .foregroundColor(.white.opacity(0.9))
                .scrollContentBackground(.hidden)
                .padding(6)
                .frame(height: 240)
                .background(Color.zinc800)
                .cornerRadius(6)

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

            HStack {
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add") {
                    let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !t.isEmpty else { return }
                    let desc = description.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task {
                        await viewModel.addTask(
                            title: t, column: column, priority: priority,
                            description: desc.isEmpty ? nil : desc,
                            category: template.rawValue
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
}

private struct KanbanCardView: View {
    let task: MWProjectTask
    let attachments: [MWProjectFile]
    let onTap: () -> Void
    let onToggle: () -> Void
    let onMoveColumn: (String) -> Void

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
        kanbanColumns.first(where: { $0.key == task.boardColumn })?.label ?? task.boardColumn
    }

    private var assigneeDisplay: String? { task.displayAssignee }

    private var assigneeInitial: String? {
        guard let name = assigneeDisplay, !name.isEmpty else { return nil }
        return String(name.prefix(1)).uppercased()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Button(action: onToggle) {
                Image(systemName: task.status == "completed" ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 13))
                    .foregroundColor(task.status == "completed" ? .matcha500 : .secondary)
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 3) {
                Text(task.title)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .strikethrough(task.status == "completed")
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)

                if let note = task.progressNote, !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "location.north.line")
                            .font(.system(size: 8))
                            .foregroundColor(.matcha500)
                        Text(note)
                            .font(.system(size: 10))
                            .italic()
                            .foregroundColor(.white.opacity(0.6))
                            .lineLimit(1)
                    }
                }

                HStack(spacing: 5) {
                    Circle().fill(priorityColor).frame(width: 5, height: 5)

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

                    Menu {
                        ForEach(kanbanColumns, id: \.key) { c in
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
                            .foregroundColor(.white.opacity(0.8))
                            .tracking(0.3)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.white.opacity(0.12))
                            .cornerRadius(8)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()

                    if let initial = assigneeInitial, let name = assigneeDisplay {
                        Circle()
                            .fill(Color.white.opacity(0.12))
                            .frame(width: 14, height: 14)
                            .overlay(
                                Text(initial)
                                    .font(.system(size: 8, weight: .semibold))
                                    .foregroundColor(.white)
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
            Spacer(minLength: 0)
        }
        .padding(8)
        .background(Color.zinc800)
        .cornerRadius(6)
        .onTapGesture(perform: onTap)
    }

    /// "Added <date> · Moved <relative>" in Pacific time. Moved only shows
    /// once the card has crossed columns at least once (lastMovedAt != nil).
    @ViewBuilder
    private var timestampLine: some View {
        if let added = PacificDateFormatter.shortDate(task.createdAt) {
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
    @State private var progressNote: String
    @State private var assignedTo: String?
    @State private var uploadingName: String?
    @State private var isDragOverAttachments = false
    /// Local state. The attachment preview presents nested over this editor
    /// sheet — hoisting it out causes sibling-sheet conflict (only one
    /// `.sheet` per view on macOS) and the preview never shows until the
    /// editor dismisses.
    @State private var previewFile: MWProjectFile?

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
        _progressNote = State(initialValue: task.progressNote ?? "")
        _assignedTo = State(initialValue: task.assignedTo)
    }

    private var collaborators: [MWProjectCollaborator] { viewModel.collaborators }
    private var attachments: [MWProjectFile] { viewModel.taskFiles[task.id] ?? [] }

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
                Picker("Priority", selection: $priority) {
                    Text("Critical").tag("critical")
                    Text("High").tag("high")
                    Text("Medium").tag("medium")
                    Text("Low").tag("low")
                }
                .pickerStyle(.menu)
            }

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
                        priority: priority,
                        dueDate: dueDate.isEmpty ? nil : dueDate,
                        assignedTo: assigneeWire,
                        progressNote: progressNote
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
