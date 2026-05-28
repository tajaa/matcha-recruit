import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct TaskEditorSheet: View {
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
        .frame(width: 600)
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
