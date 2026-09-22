import SwiftUI

/// Mutations are awaited before dismissing. A failed save keeps the draft on
/// screen; editing emits only changed fields to avoid overwriting live updates.
struct MobileTaskSheet: View {
    let vm: ProjectDetailViewModel
    let projectId: String
    var task: MWProjectTask? = nil
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var details = ""
    @State private var priority = "medium"
    @State private var column = "todo"
    @State private var assignee = ""
    @State private var hasDueDate = false
    @State private var dueDate = Date()
    @State private var subtaskTitle = ""
    @State private var comment = ""
    @State private var reviewNote = ""
    @State private var subtasks: [MWSubtask] = []
    @State private var history: [MWTaskHistoryEntry] = []
    @State private var files: [MWProjectFile] = []
    @State private var busy = false
    @State private var error: String?
    @State private var deleteConfirmation = false
    @State private var importing = false
    @State private var didSeed = false
    @State private var discardConfirmation = false
    private let service = MatchaWorkService.shared
    private var liveTask: MWProjectTask? { vm.tasks.first { $0.id == task?.id } ?? task }
    private var currentSubtasks: [MWSubtask] {
        let round = subtasks.map { $0.roundIndex ?? 1 }.max() ?? 1
        return subtasks.filter { ($0.roundIndex ?? 1) == round }
    }
    private var hasChanges: Bool {
        title != (task?.title ?? "") || details != (task?.description ?? "")
            || priority != (task?.priority ?? "medium") || column != (task?.boardColumn ?? "todo")
            || assignee != (task?.assignedTo ?? "")
            || (hasDueDate ? MobileTaskDates.string(dueDate) : "") != (task?.dueDate.map { String($0.prefix(10)) } ?? "")
            || !comment.isEmpty || !subtaskTitle.isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("The next small step") {
                    TextField("Task title", text: $title, axis: .vertical).font(.headline)
                    TextField("Description, context, or a useful link…", text: $details, axis: .vertical).lineLimit(4...12)
                }
                Section("Details") {
                    Picker("Status", selection: $column) { ForEach(kanbanColumns, id: \.key) { Text($0.label).tag($0.key) } }
                    Picker("Priority", selection: $priority) { ForEach(["low", "medium", "high", "critical"], id: \.self) { Text($0.capitalized).tag($0) } }
                    Picker("Assigned to", selection: $assignee) {
                        Text("Unassigned").tag("")
                        ForEach(vm.collaborators) { Text($0.name).tag($0.userId) }
                        if !assignee.isEmpty && !vm.collaborators.contains(where: { $0.userId == assignee }) {
                            Text(task?.displayAssignee ?? "Current assignee").tag(assignee)
                        }
                    }
                    Toggle("Due date", isOn: $hasDueDate)
                    if hasDueDate { DatePicker("Due", selection: $dueDate, displayedComponents: .date) }
                }
                if let task {
                    checklist(task)
                    review(task)
                    Section("Attachments") {
                        ForEach(files) { MobileFileLink(file: $0) }
                        Button("Attach a file", systemImage: "paperclip") { importing = true }
                    }
                    Section("Conversation & activity") {
                        TextField("Leave an update…", text: $comment, axis: .vertical).lineLimit(2...6)
                        Button("Post update", systemImage: "arrow.up.circle") {
                            run {
                                try await service.logTaskActivity(projectId: projectId, taskId: task.id, kind: "note", body: comment.trimmingCharacters(in: .whitespacesAndNewlines))
                                comment = ""
                                await loadHistory(task.id)
                            }
                        }.disabled(comment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        ForEach(history) { item in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(item.actorName ?? "Project activity").font(.caption.weight(.semibold)).foregroundStyle(EspressoStyle.accent)
                                Text(item.metadata?["body"] ?? item.toValue ?? item.eventType.replacingOccurrences(of: "_", with: " ").capitalized).font(.subheadline)
                                Text(PacificDateFormatter.absolute(item.createdAt) ?? item.createdAt).font(.caption2).foregroundStyle(.secondary)
                            }.padding(.vertical, 4)
                        }
                    }
                    Section { Button("Delete task", role: .destructive) { deleteConfirmation = true } }
                }
                if let error { Section { Text(error).foregroundStyle(.red).textSelection(.enabled) } }
            }
            .disabled(busy || vm.project?.mobileCanEdit != true)
            .scrollContentBackground(.hidden).espressoBackground()
            .navigationTitle(task == nil ? "New task" : "Task").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { if hasChanges { discardConfirmation = true } else { dismiss() } }.disabled(busy)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "Saving…" : "Save") { run { try await save(); dismiss() } }
                        .disabled(busy || vm.project?.mobileCanEdit != true || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .interactiveDismissDisabled(busy || hasChanges)
            .confirmationDialog("Discard unsaved edits? Updates already posted will stay saved.", isPresented: $discardConfirmation, titleVisibility: .visible) {
                Button("Discard edits", role: .destructive) { dismiss() }
            }
            .confirmationDialog("Permanently delete this task?", isPresented: $deleteConfirmation, titleVisibility: .visible) {
                Button("Delete task", role: .destructive) {
                    guard let task else { return }
                    run {
                        try await service.deleteProjectTask(projectId: projectId, taskId: task.id)
                        vm.tasks.removeAll { $0.id == task.id }; dismiss()
                    }
                }
            }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.item]) { result in
                guard let task else { return }
                run {
                    let upload = try await MobileFileUpload.read(result.get())
                    let file = try await service.uploadTaskFile(projectId: projectId, taskId: task.id, file: upload)
                    files.append(file); vm.taskFiles[task.id] = files
                }
            }
            .task {
                guard !didSeed else { return }
                didSeed = true
                seed()
                if let task { await loadDetails(task.id) }
            }
        }.tint(EspressoStyle.accent)
    }

    private func checklist(_ task: MWProjectTask) -> some View {
        Section("Checklist") {
            ForEach(currentSubtasks) { item in
                Button {
                    run {
                        let updated = try await service.setSubtaskDone(projectId: projectId, taskId: task.id, subtaskId: item.id, isDone: !item.isDone)
                        if let index = subtasks.firstIndex(where: { $0.id == item.id }) { subtasks[index] = updated }
                        syncChecklist(task.id)
                    }
                } label: {
                    Label(item.title, systemImage: item.isDone ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(item.isDone ? EspressoStyle.sage : Color.primary)
                }.accessibilityValue(item.isDone ? "Complete" : "Incomplete")
                    .swipeActions {
                        Button("Delete", role: .destructive) {
                            run {
                                try await service.deleteSubtask(projectId: projectId, taskId: task.id, subtaskId: item.id)
                                subtasks.removeAll { $0.id == item.id }; syncChecklist(task.id)
                            }
                        }
                    }
            }
            HStack {
                TextField("Add a small step", text: $subtaskTitle)
                Button("Add") {
                    run {
                        let item = try await service.createSubtask(projectId: projectId, taskId: task.id, title: subtaskTitle.trimmingCharacters(in: .whitespacesAndNewlines))
                        subtasks.append(item); subtaskTitle = ""; syncChecklist(task.id)
                    }
                }.disabled(subtaskTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            if subtasks.count > currentSubtasks.count {
                Text("Showing the current round. Earlier review rounds are available on desktop.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private func review(_ task: MWProjectTask) -> some View {
        if let note = liveTask?.reviewNote, !note.isEmpty { Section("Changes requested") { Text(note) } }
        if liveTask?.boardColumn == "review" {
            Section("Review this work") {
                TextField("Feedback (required to request changes)", text: $reviewNote, axis: .vertical)
                Button("Approve & complete", systemImage: "checkmark.seal") {
                    run {
                        let updated = try await service.approveTask(projectId: projectId, taskId: task.id, note: reviewNote)
                        vm.replacePreservingAggregates(updated); column = updated.boardColumn
                        await loadHistory(task.id)
                    }
                }
                Button("Request changes", systemImage: "arrow.uturn.backward") {
                    run {
                        let updated = try await service.rejectTask(projectId: projectId, taskId: task.id, note: reviewNote.trimmingCharacters(in: .whitespacesAndNewlines))
                        vm.replacePreservingAggregates(updated); column = updated.boardColumn
                        await loadHistory(task.id)
                    }
                }.disabled(reviewNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    private func seed() {
        guard let task else { return }
        title = task.title; details = task.description ?? ""; priority = task.priority
        column = task.boardColumn; assignee = task.assignedTo ?? ""
        hasDueDate = task.dueDate?.isEmpty == false
        dueDate = MobileTaskDates.parse(task.dueDate) ?? Date()
    }

    private func save() async throws {
        let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let due = hasDueDate ? MobileTaskDates.string(dueDate) : ""
        if let task {
            var patch = MatchaWorkService.ProjectTaskPatch()
            if name != task.title { patch.title = name }
            if details != (task.description ?? "") { patch.description = details }
            if priority != task.priority { patch.priority = priority }
            if column != task.boardColumn { patch.boardColumn = column }
            if assignee != (task.assignedTo ?? "") { patch.assignedTo = assignee }
            if due != (task.dueDate.map { String($0.prefix(10)) } ?? "") { patch.dueDate = due }
            let updated = try await service.updateProjectTask(projectId: projectId, taskId: task.id, patch: patch)
            vm.replacePreservingAggregates(updated)
        } else {
            let created = try await service.createProjectTask(projectId: projectId, title: name, boardColumn: column,
                description: details, priority: priority, dueDate: due.isEmpty ? nil : due, assignedTo: assignee.isEmpty ? nil : assignee)
            if !vm.tasks.contains(where: { $0.id == created.id }) { vm.tasks.insert(created, at: 0) }
        }
    }

    private func run(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true; error = nil
        Task {
            defer { busy = false }
            do { try await operation() } catch { self.error = error.localizedDescription }
        }
    }

    private func syncChecklist(_ id: String) {
        vm.taskSubtasks[id] = subtasks; vm.syncSubtaskCounts(taskId: id)
    }
    private func loadHistory(_ id: String) async {
        do { history = try await service.fetchTaskHistory(projectId: projectId, taskId: id) }
        catch { self.error = error.localizedDescription }
    }
    private func loadDetails(_ id: String) async {
        do { subtasks = try await service.listSubtasks(projectId: projectId, taskId: id); syncChecklist(id) }
        catch { self.error = error.localizedDescription }
        do { files = try await service.listTaskFiles(projectId: projectId, taskId: id) }
        catch { self.error = error.localizedDescription }
        await loadHistory(id)
    }
}
