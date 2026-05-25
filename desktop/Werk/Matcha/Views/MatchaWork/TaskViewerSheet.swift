import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// Read-only modal that opens on a kanban card tap. Surfaces title,
/// description, due date, assignee, and attachments. The user clicks
/// "Edit" to escalate into `TaskEditorSheet`; passive viewing no longer
/// drops them straight into edit mode.
///
/// Click an attachment → opens `AttachmentPreviewSheet` nested over this
/// viewer (same pattern that works in TaskEditorSheet).
struct TaskViewerSheet: View {
    let task: MWProjectTask
    @Bindable var viewModel: ProjectDetailViewModel
    let onEdit: () -> Void
    let onClose: () -> Void

    @State private var previewFile: MWProjectFile?
    @State private var history: [MWTaskHistoryEntry] = []
    @State private var didCopy = false
    @State private var isCopying = false
    @State private var newNote = ""
    @State private var addingNote = false
    @State private var isRejecting = false
    @State private var rejectNote = ""
    @State private var submitting = false
    @State private var newSubtask = ""
    @State private var addingSubtask = false

    private var attachments: [MWProjectFile] {
        viewModel.taskFiles[task.id] ?? []
    }

    /// Checklist items for this task (ordered). Mutated optimistically by the
    /// view model; the card-face "done/total" stays in sync via syncSubtaskCounts.
    private var subtasks: [MWSubtask] {
        viewModel.taskSubtasks[task.id] ?? []
    }
    private var subtaskDoneCount: Int { subtasks.filter { $0.isDone }.count }

    /// Free-form notes/comments — the `activity` rows from the task history.
    private var notes: [MWTaskHistoryEntry] {
        history.filter { $0.eventType == "activity" }
    }

    private var assigneeName: String? {
        // Prefer the server-provided assignee (clean name with email-derived
        // fallback in MWProjectTask.displayAssignee). Fall back to a local
        // collaborator-list lookup if the task came from a path that didn't
        // include assigned_name (older REST shapes, optimistic updates).
        if let display = task.displayAssignee { return display }
        guard let id = task.assignedTo else { return nil }
        return viewModel.collaborators.first(where: { $0.userId == id })?.name
    }

    private var columnLabel: String {
        task.boardColumn
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text(task.title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                Spacer()
                Button {
                    Task { await copyTicketToClipboard() }
                } label: {
                    if isCopying {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: didCopy ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 11))
                            .foregroundColor(didCopy ? .matcha500 : .secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(isCopying)
                .help("Copy ticket (markdown + screenshots)")
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 6) {
                metaPill(label: columnLabel, color: .matcha500)
                metaPill(label: task.priority.capitalized, color: .secondary)
                if let due = task.dueDate, !due.isEmpty {
                    metaPill(label: "Due \(String(due.prefix(10)))", color: .secondary)
                }
                if let name = assigneeName {
                    metaPill(label: name, color: .secondary)
                }
                if let elName = task.elementName
                    ?? viewModel.elements.first(where: { $0.id == task.elementId })?.name {
                    HStack(spacing: 3) {
                        Image(systemName: "square.stack.3d.up.fill").font(.system(size: 8))
                        Text(elName).font(.system(size: 9, weight: .semibold))
                    }
                    .foregroundColor(.matcha500)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Color.matcha500.opacity(0.15)).cornerRadius(3)
                }
                Spacer()
            }

            if PacificDateFormatter.absolute(task.createdAt) != nil
                || PacificDateFormatter.absolute(task.lastMovedAt) != nil {
                HStack(spacing: 8) {
                    if let added = PacificDateFormatter.absolute(task.createdAt) {
                        Label("Added \(added)", systemImage: "plus.circle")
                    }
                    if let moved = PacificDateFormatter.absolute(task.lastMovedAt) {
                        Label("Moved \(moved)", systemImage: "arrow.left.arrow.right")
                    }
                    Spacer()
                }
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            }

            if let note = task.reviewNote?.trimmingCharacters(in: .whitespacesAndNewlines),
               !note.isEmpty,
               task.boardColumn == "changes_requested" || task.boardColumn == "in_progress" {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 5) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 10))
                        Text("NEEDS WORK")
                            .font(.system(size: 9, weight: .semibold))
                            .tracking(0.5)
                    }
                    .foregroundColor(.orange)
                    Text(note)
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.9))
                        .textSelection(.enabled)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.12))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.orange.opacity(0.4), lineWidth: 1)
                )
                .cornerRadius(6)
            }

            if let description = task.description, !description.isEmpty {
                ScrollView {
                    Text(description)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.85))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                .frame(maxHeight: 220)
                .padding(10)
                .background(Color.zinc800.opacity(0.5))
                .cornerRadius(6)
            }

            if let progress = task.progressNote, !progress.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("WHERE WE'RE AT")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.matcha500)
                        .tracking(0.5)
                    Text(progress)
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.9))
                        .textSelection(.enabled)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.matcha500.opacity(0.1))
                .cornerRadius(6)
            }

            // Notes (event_type == activity) get their own section above, so
            // the timeline shows only structural events to avoid duplication.
            let timelineEntries = history.filter { $0.eventType != "activity" }
            if !timelineEntries.isEmpty {
                TaskHistoryTimeline(entries: timelineEntries)
            }

            if !attachments.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        Image(systemName: "paperclip")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                        Text("ATTACHMENTS")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                            .tracking(0.5)
                        Text("\(attachments.count)")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                    }
                    VStack(spacing: 3) {
                        ForEach(attachments) { f in
                            ViewerAttachmentRow(file: f) {
                                previewFile = f
                            }
                        }
                    }
                }
            }

            checklistSection

            notesSection

            if isRejecting {
                rejectEditor
            }

            HStack(spacing: 12) {
                if task.boardColumn == "review" && !isRejecting {
                    Button {
                        isRejecting = true
                        rejectNote = ""
                    } label: {
                        Label("Send back", systemImage: "arrow.uturn.backward")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.orange)
                    }
                    .buttonStyle(.plain)
                    .help("Mark incomplete and send to Changes Requested — notifies the assignee")
                }
                Spacer()
                Button("Edit") { onEdit() }
                    .buttonStyle(.plain)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.matcha500)
            }
        }
        .padding(16)
        .frame(width: 460)
        .background(Color.appBackground)
        .task {
            if viewModel.taskFiles[task.id] == nil {
                await viewModel.loadTaskFiles(taskId: task.id)
            }
            await viewModel.loadSubtasks(taskId: task.id)
            await loadHistory()
        }
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
    }

    private func loadHistory() async {
        guard let pid = viewModel.project?.id else { return }
        if let rows = try? await MatchaWorkService.shared.fetchTaskHistory(
            projectId: pid, taskId: task.id
        ) {
            history = rows
        }
    }

    // MARK: - Notes / comments

    @ViewBuilder
    private var notesSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "text.bubble")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("NOTES")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if !notes.isEmpty {
                    Text("\(notes.count)")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
            }

            ForEach(notes) { n in
                let body = (n.metadata?["body"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                if !body.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(body)
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.9))
                            .textSelection(.enabled)
                        Text("\((n.actorName?.isEmpty == false ? n.actorName! : "Someone")) · \(PacificDateFormatter.absolute(n.createdAt) ?? "")")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.zinc800.opacity(0.5))
                    .cornerRadius(5)
                }
            }

            HStack(spacing: 6) {
                TextField("Add a note…", text: $newNote)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .padding(7)
                    .background(Color.zinc800.opacity(0.6))
                    .cornerRadius(5)
                    .onSubmit { Task { await submitNote() } }
                Button {
                    Task { await submitNote() }
                } label: {
                    if addingNote {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Add").font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.matcha500)
                    }
                }
                .buttonStyle(.plain)
                .disabled(addingNote || newNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    // MARK: - Checklist (subtasks)

    @ViewBuilder
    private var checklistSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "checklist")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("CHECKLIST")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if !subtasks.isEmpty {
                    Text("\(subtaskDoneCount)/\(subtasks.count)")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
            }

            ForEach(subtasks) { item in
                SubtaskRow(
                    item: item,
                    onToggle: {
                        Task { await viewModel.toggleSubtask(taskId: task.id, subtaskId: item.id, isDone: !item.isDone) }
                    },
                    onDelete: {
                        Task { await viewModel.deleteSubtask(taskId: task.id, subtaskId: item.id) }
                    }
                )
            }

            HStack(spacing: 6) {
                TextField("Add a checklist item…", text: $newSubtask)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .padding(7)
                    .background(Color.zinc800.opacity(0.6))
                    .cornerRadius(5)
                    .onSubmit { submitSubtask() }
                Button {
                    submitSubtask()
                } label: {
                    if addingSubtask {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Add").font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.matcha500)
                    }
                }
                .buttonStyle(.plain)
                .disabled(addingSubtask || newSubtask.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }

    private func submitSubtask() {
        let text = newSubtask.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !addingSubtask else { return }
        addingSubtask = true
        Task {
            await viewModel.addSubtask(taskId: task.id, title: text)
            await MainActor.run { newSubtask = ""; addingSubtask = false }
        }
    }

    // MARK: - Reviewer send-back

    @ViewBuilder
    private var rejectEditor: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("WHAT'S INCOMPLETE?")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(.orange)
                .tracking(0.5)
            TextEditor(text: $rejectNote)
                .font(.system(size: 12))
                .foregroundColor(.white.opacity(0.9))
                .scrollContentBackground(.hidden)
                .padding(5)
                .frame(height: 64)
                .background(Color.zinc800.opacity(0.6))
                .cornerRadius(5)

            // Re-open specific checklist items as part of sending back, so the
            // assignee knows exactly which pieces need rework. Only completed
            // items are candidates; tapping flips them back to not-done live.
            if subtasks.contains(where: { $0.isDone }) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("RE-OPEN ITEMS")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.orange)
                        .tracking(0.5)
                    ForEach(subtasks.filter { $0.isDone }) { item in
                        Button {
                            Task { await viewModel.toggleSubtask(taskId: task.id, subtaskId: item.id, isDone: false) }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 11))
                                    .foregroundColor(.matcha500)
                                Text(item.title)
                                    .font(.system(size: 11))
                                    .foregroundColor(.white.opacity(0.85))
                                    .strikethrough()
                                    .lineLimit(1)
                                Spacer()
                                Text("Re-open")
                                    .font(.system(size: 9, weight: .semibold))
                                    .foregroundColor(.orange)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            HStack {
                Button("Cancel") { isRejecting = false; rejectNote = "" }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Spacer()
                Button {
                    Task { await submitReject() }
                } label: {
                    if submitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Send back")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.orange)
                    }
                }
                .buttonStyle(.plain)
                .disabled(submitting || rejectNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(10)
        .background(Color.orange.opacity(0.08))
        .cornerRadius(6)
    }

    private func submitNote() async {
        let text = newNote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let pid = viewModel.project?.id, !addingNote else { return }
        addingNote = true
        defer { addingNote = false }
        do {
            try await MatchaWorkService.shared.logTaskActivity(
                projectId: pid, taskId: task.id, kind: "note", body: text
            )
            newNote = ""
            await loadHistory()
        } catch {
            // Best-effort; leave the text in place so the user can retry.
        }
    }

    private func submitReject() async {
        let note = rejectNote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !note.isEmpty, !submitting else { return }
        submitting = true
        let ok = await viewModel.rejectTask(id: task.id, note: note)
        submitting = false
        if ok {
            isRejecting = false
            rejectNote = ""
            onClose()
        }
    }

    /// Copies the ticket as markdown PLUS the real screenshot bytes, so pasting
    /// into Claude/ChatGPT web drops the actual images instead of dead
    /// presigned/CloudFront URLs. The markdown (which still lists every image as
    /// a `![](url)` line) doubles as the fallback for images that fail to
    /// download or for paste targets that ignore image flavors.
    ///
    /// The primary pasteboard item carries BOTH the markdown string and the
    /// first image's bytes, so a single paste can surface either flavor. Extra
    /// images ride on follow-up items (best-effort — browsers typically pull
    /// only one image per paste).
    @MainActor
    private func copyTicketToClipboard() async {
        isCopying = true
        let markdown = TaskClipboardExporter.markdown(
            for: task,
            assigneeName: assigneeName,
            columnLabel: columnLabel,
            attachments: attachments,
        )

        // Download up to 6 image attachments' bytes.
        let images = Array(attachments.filter { $0.isImage }.prefix(6))
        var downloaded: [(file: MWProjectFile, data: Data)] = []
        for img in images {
            guard let url = URL(string: img.storageUrl) else { continue }
            if let (data, _) = try? await URLSession.shared.data(from: url) {
                downloaded.append((img, data))
            }
        }

        let primary = NSPasteboardItem()
        primary.setString(markdown, forType: .string)
        if let first = downloaded.first {
            primary.setData(first.data, forType: pasteboardType(for: first.file))
        }
        var items = [primary]
        for entry in downloaded.dropFirst() {
            let item = NSPasteboardItem()
            item.setData(entry.data, forType: pasteboardType(for: entry.file))
            items.append(item)
        }

        let board = NSPasteboard.general
        board.clearContents()
        board.writeObjects(items)

        isCopying = false
        didCopy = true
        Task {
            try? await Task.sleep(for: .milliseconds(1500))
            await MainActor.run { didCopy = false }
        }
    }

    /// Concrete image pasteboard type so the receiver knows the format.
    private func pasteboardType(for file: MWProjectFile) -> NSPasteboard.PasteboardType {
        let ct = (file.contentType ?? "").lowercased()
        let ext = (file.filename as NSString).pathExtension.lowercased()
        if ct.contains("png") || ext == "png" { return .png }
        if ct.contains("tiff") || ext == "tiff" || ext == "tif" { return .tiff }
        if ct.contains("jpeg") || ct.contains("jpg") || ext == "jpg" || ext == "jpeg" {
            return NSPasteboard.PasteboardType(UTType.jpeg.identifier)
        }
        if let ut = UTType(filenameExtension: ext), ut.conforms(to: .image) {
            return NSPasteboard.PasteboardType(ut.identifier)
        }
        return .png
    }

    private func metaPill(label: String, color: Color) -> some View {
        Text(label)
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(3)
    }
}

/// One checklist row in the TaskViewerSheet: toggle checkbox + title, delete on
/// hover. Done items strike through and dim. Dark-themed to match the sheet.
private struct SubtaskRow: View {
    let item: MWSubtask
    let onToggle: () -> Void
    let onDelete: () -> Void
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onToggle) {
                Image(systemName: item.isDone ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 13))
                    .foregroundColor(item.isDone ? .matcha500 : .secondary)
            }
            .buttonStyle(.plain)
            Text(item.title)
                .font(.system(size: 12))
                .foregroundColor(item.isDone ? .secondary : .white)
                .strikethrough(item.isDone)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
            Spacer(minLength: 0)
            if isHovered {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 10))
                        .foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("Delete item")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(isHovered ? Color.zinc800.opacity(0.6) : Color.clear)
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
    }
}

private struct ViewerAttachmentRow: View {
    let file: MWProjectFile
    let onTap: () -> Void
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
                .font(.system(size: 12))
                .foregroundColor(.secondary)
            Text(file.filename)
                .font(.system(size: 11))
                .foregroundColor(.white)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer()
            Text(sizeLabel)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(isHovered ? Color.zinc800.opacity(0.8) : Color.zinc800.opacity(0.5))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture(perform: onTap)
    }
}

/// Builds a clipboard-friendly markdown blob describing a task. Used by
/// TaskViewerSheet's Copy button so the user can drop the full ticket
/// (title, status, assignee, description, progress note, attachments,
/// history) into Claude Code / Codex / ChatGPT / any chat that accepts
/// markdown. Image attachments are inlined as `![]()` so paste-targets
/// that fetch URLs render the screenshots; terminal paste-targets see
/// the URL as text.
enum TaskClipboardExporter {
    static func markdown(
        for task: MWProjectTask,
        assigneeName: String?,
        columnLabel: String,
        attachments: [MWProjectFile],
    ) -> String {
        var lines: [String] = []
        lines.append("# \(task.title)")
        lines.append("")

        var metaParts: [String] = [
            "**Status:** \(columnLabel)",
            "**Priority:** \(task.priority.capitalized)",
        ]
        metaParts.append("**Assignee:** \(assigneeName ?? "Unassigned")")
        if let due = task.dueDate, !due.isEmpty {
            metaParts.append("**Due:** \(String(due.prefix(10)))")
        }
        lines.append(metaParts.joined(separator: " · "))
        lines.append("")

        lines.append("## Description")
        let description = (task.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        lines.append(description.isEmpty ? "_(no description)_" : description)
        lines.append("")

        lines.append("## Where We're At")
        let progress = (task.progressNote ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        lines.append(progress.isEmpty ? "_(no progress note)_" : progress)
        lines.append("")

        if !attachments.isEmpty {
            lines.append("## Attachments (\(attachments.count))")
            for f in attachments {
                let sizeStr = formatSize(f.fileSize)
                lines.append("- [\(f.filename)](\(f.storageUrl)) — \(sizeStr)")
            }
            // Inline-render images so paste-targets that fetch URLs show them.
            for f in attachments where f.isImage {
                lines.append("")
                lines.append("![\(f.filename)](\(f.storageUrl))")
            }
            lines.append("")
        }

        return lines.joined(separator: "\n")
    }

    private static func columnLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func formatSize(_ bytes: Int) -> String {
        let b = Double(bytes)
        if b < 1024 { return "\(bytes) B" }
        if b < 1024 * 1024 { return String(format: "%.1f KB", b / 1024) }
        return String(format: "%.1f MB", b / 1024 / 1024)
    }
}
