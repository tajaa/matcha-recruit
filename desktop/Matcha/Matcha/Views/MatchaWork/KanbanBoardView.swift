import SwiftUI

private let kanbanColumns: [(key: String, label: String)] = [
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("done", "Done"),
]

struct KanbanBoardView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var editingTask: MWProjectTask?
    /// Inline-add: which column has its inline TextField visible. Set by the
    /// `+` button on the column header; cleared by Esc / blur / submit.
    @State private var inlineAddColumn: String?
    @State private var inlineAddTitle: String = ""
    @State private var hoveredEmptyColumn: String?
    /// Legacy modal sheet still wired for keyboard-discoverability fallback;
    /// inline path is the default.
    @State private var newTaskColumn: String?
    @State private var newTaskTitle: String = ""

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
        .sheet(item: $editingTask) { task in
            TaskEditorSheet(task: task) { patch in
                Task {
                    await viewModel.updateTask(id: task.id, patch: patch)
                    editingTask = nil
                }
            } onDelete: {
                Task {
                    await viewModel.deleteTask(id: task.id)
                    editingTask = nil
                }
            } onClose: {
                editingTask = nil
            }
        }
        .sheet(isPresented: Binding(get: { newTaskColumn != nil }, set: { if !$0 { newTaskColumn = nil; newTaskTitle = "" } })) {
            newTaskSheet
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
                Button {
                    inlineAddColumn = key
                    inlineAddTitle = ""
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Add task (Enter to save, Esc to cancel)")
            }
            .padding(.horizontal, 8)
            .padding(.top, 6)

            if isInlineAdding {
                inlineAddRow(column: key)
            }

            ScrollView {
                LazyVStack(spacing: 6) {
                    ForEach(colTasks) { task in
                        KanbanCardView(task: task) {
                            editingTask = task
                        } onToggle: {
                            Task { await viewModel.toggleTaskComplete(id: task.id) }
                        }
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
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
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

    private var newTaskSheet: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("New Task")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
            TextField("Title", text: $newTaskTitle)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)
            HStack {
                Button("Cancel") {
                    newTaskColumn = nil
                    newTaskTitle = ""
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)
                Spacer()
                Button("Add") {
                    let title = newTaskTitle.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !title.isEmpty, let col = newTaskColumn else { return }
                    Task {
                        await viewModel.addTask(title: title, column: col)
                        newTaskColumn = nil
                        newTaskTitle = ""
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(.matcha500)
                .disabled(newTaskTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 340)
        .background(Color.appBackground)
    }
}

private struct KanbanCardView: View {
    let task: MWProjectTask
    let onTap: () -> Void
    let onToggle: () -> Void

    private var priorityColor: Color {
        switch task.priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .secondary
        }
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

                HStack(spacing: 5) {
                    Circle().fill(priorityColor).frame(width: 5, height: 5)
                    if let name = task.assignedName, !name.isEmpty {
                        Text(name)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
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
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .background(Color.zinc800)
        .cornerRadius(6)
        .onTapGesture(perform: onTap)
    }
}

private struct TaskEditorSheet: View {
    let task: MWProjectTask
    let onSave: (MatchaWorkService.ProjectTaskPatch) -> Void
    let onDelete: () -> Void
    let onClose: () -> Void

    @State private var title: String
    @State private var description: String
    @State private var priority: String
    @State private var dueDate: String
    @State private var boardColumn: String

    init(
        task: MWProjectTask,
        onSave: @escaping (MatchaWorkService.ProjectTaskPatch) -> Void,
        onDelete: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.task = task
        self.onSave = onSave
        self.onDelete = onDelete
        self.onClose = onClose
        _title = State(initialValue: task.title)
        _description = State(initialValue: task.description ?? "")
        _priority = State(initialValue: task.priority)
        _dueDate = State(initialValue: task.dueDate.map { String($0.prefix(10)) } ?? "")
        _boardColumn = State(initialValue: task.boardColumn)
    }

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

            TextField("Due date (YYYY-MM-DD, optional)", text: $dueDate)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.zinc800)
                .cornerRadius(6)

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
                    let patch = MatchaWorkService.ProjectTaskPatch(
                        title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                        description: description,
                        boardColumn: boardColumn,
                        priority: priority,
                        dueDate: dueDate.isEmpty ? nil : dueDate
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
    }
}
