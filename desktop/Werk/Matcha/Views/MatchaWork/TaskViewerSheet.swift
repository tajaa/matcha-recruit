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
    /// Pending image attachments queued for the next note submit. Cleared
    /// after a successful submit. Each entry is held in-memory until upload.
    @State private var pendingAttachments: [PendingAttachment] = []

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

            // "You are here" banner — at-a-glance answer to "what state is
            // this ticket in and who owns the next move?" Anchors the rest
            // of the sheet (rounds, checklist) so the reader doesn't have
            // to reason from column chips + history to figure it out.
            stateBanner

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

            // New section order matches how a ticket actually gets finished:
            // concrete remaining work first (checklist), then a unified
            // round-grouped discussion feed (notes + subtask events + status
            // moves, organized by review-cycle round so each "send back →
            // rework → re-review" pass reads as one block), then the
            // task-level file dump.
            checklistSection

            discussionSection

            if !attachments.isEmpty {
                attachmentsSection
            }

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
        .frame(width: 600)
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

    // MARK: - "You are here" state banner

    private struct StatePhase {
        let label: String
        let owner: String
        let color: Color
        let icon: String
    }

    private var currentPhase: StatePhase {
        switch task.boardColumn {
        case "todo":
            return StatePhase(label: "Not Started", owner: "Assignee to begin", color: .secondary, icon: "circle.dashed")
        case "in_progress":
            return StatePhase(label: "In Progress", owner: "Assignee working", color: .yellow, icon: "hammer.fill")
        case "review":
            return StatePhase(label: "In Review", owner: "Reviewer to assess", color: .blue, icon: "magnifyingglass.circle.fill")
        case "changes_requested":
            return StatePhase(label: "Changes Requested", owner: "Assignee to address feedback", color: .orange, icon: "arrow.uturn.backward.circle.fill")
        case "done":
            return StatePhase(label: "Done", owner: "Closed", color: .matcha500, icon: "checkmark.seal.fill")
        default:
            return StatePhase(label: columnLabel, owner: "", color: .secondary, icon: "circle")
        }
    }

    @ViewBuilder
    private var stateBanner: some View {
        let p = currentPhase
        HStack(spacing: 10) {
            Image(systemName: p.icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(p.color)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text("YOU ARE HERE")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                        .tracking(0.7)
                    Text("·")
                        .font(.system(size: 8))
                        .foregroundColor(.secondary)
                    Text(p.label)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(p.color)
                }
                if !p.owner.isEmpty {
                    Text(p.owner)
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.7))
                }
            }
            Spacer()
            if rounds.count > 0 {
                Text("Round \(rounds.count)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(p.color)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(p.color.opacity(0.15))
                    .cornerRadius(3)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(p.color.opacity(0.1))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(p.color.opacity(0.4), lineWidth: 1)
        )
        .cornerRadius(6)
    }

    // MARK: - Discussion (rounds-grouped feed)

    /// All history events grouped into review-cycle rounds. Round 1 starts at
    /// task creation; a new round opens every time the card leaves `review`
    /// for a non-done column (changes_requested / in_progress / todo). The
    /// "leaving review" event itself lands at the top of the new round so it
    /// reads "Reviewer sent back · …" + the assignee's reply notes.
    private var rounds: [TaskRound] {
        TaskRound.build(from: history)
    }

    @ViewBuilder
    private var discussionSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("DISCUSSION")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if !rounds.isEmpty {
                    Text("\(rounds.count) round\(rounds.count == 1 ? "" : "s")")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
            }

            noteComposer

            // Rounds rendered newest-first so the active round sits right
            // under the composer. Within each round events stay chronological
            // (oldest → newest) so the round reads as a coherent story.
            ForEach(rounds.reversed()) { round in
                RoundView(
                    round: round,
                    files: attachments,
                    onPreview: { previewFile = $0 }
                )
            }
        }
    }

    @ViewBuilder
    private var noteComposer: some View {
        VStack(alignment: .leading, spacing: 6) {
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
                    attachFileFromDisk()
                } label: {
                    Image(systemName: "paperclip")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Attach a file (image / PDF)")
                Button {
                    attachImageFromClipboard()
                } label: {
                    Image(systemName: "doc.on.clipboard")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Paste screenshot from clipboard")
                Button {
                    Task { await submitNote() }
                } label: {
                    if addingNote {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Add").font(.system(size: 12, weight: .semibold))
                            .foregroundColor(canSubmitNote ? .matcha500 : .secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSubmitNote || addingNote)
            }

            if !pendingAttachments.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(pendingAttachments) { att in
                            PendingAttachmentChip(attachment: att) {
                                pendingAttachments.removeAll { $0.id == att.id }
                            }
                        }
                    }
                }
            }
        }
    }

    private var canSubmitNote: Bool {
        let hasText = !newNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return hasText || !pendingAttachments.isEmpty
    }

    private func attachFileFromDisk() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.image, .pdf]
        panel.begin { resp in
            guard resp == .OK else { return }
            for url in panel.urls {
                guard let data = try? Data(contentsOf: url) else { continue }
                let filename = url.lastPathComponent
                let mime = mimeTypeFor(filename: filename, fallback: "application/octet-stream")
                pendingAttachments.append(PendingAttachment(data: data, filename: filename, mimeType: mime))
            }
        }
    }

    private func attachImageFromClipboard() {
        let pb = NSPasteboard.general
        // Prefer PNG (lossless screenshot), then TIFF, then JPEG. Cmd+Shift+4
        // screenshots-to-clipboard land as PNG; Cmd+C on an image in Preview
        // typically lands as TIFF.
        if let png = pb.data(forType: .png) {
            pendingAttachments.append(PendingAttachment(
                data: png,
                filename: clipboardScreenshotName(ext: "png"),
                mimeType: "image/png"
            ))
            return
        }
        if let tiff = pb.data(forType: .tiff),
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            pendingAttachments.append(PendingAttachment(
                data: png,
                filename: clipboardScreenshotName(ext: "png"),
                mimeType: "image/png"
            ))
            return
        }
        let jpegType = NSPasteboard.PasteboardType(UTType.jpeg.identifier)
        if let jpeg = pb.data(forType: jpegType) {
            pendingAttachments.append(PendingAttachment(
                data: jpeg,
                filename: clipboardScreenshotName(ext: "jpg"),
                mimeType: "image/jpeg"
            ))
            return
        }
    }

    private func clipboardScreenshotName(ext: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd-HHmmss"
        return "screenshot-\(f.string(from: Date())).\(ext)"
    }

    private func mimeTypeFor(filename: String, fallback: String) -> String {
        let ext = (filename as NSString).pathExtension.lowercased()
        if let ut = UTType(filenameExtension: ext),
           let mime = ut.preferredMIMEType { return mime }
        return fallback
    }

    // MARK: - Attachments (task-level files)

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
        let pending = pendingAttachments
        guard (canSubmitNote), let pid = viewModel.project?.id, !addingNote else { return }
        addingNote = true
        defer { addingNote = false }

        // Upload pending attachments first; collect ids. A single upload
        // failure aborts so we never post a note with dangling references.
        var uploadedIds: [String] = []
        for att in pending {
            guard let id = await viewModel.uploadTaskFile(
                taskId: task.id,
                data: att.data,
                filename: att.filename,
                mimeType: att.mimeType
            ) else {
                // viewModel.errorMessage was set; keep text + chips so the
                // user can retry.
                return
            }
            uploadedIds.append(id)
        }

        do {
            try await MatchaWorkService.shared.logTaskActivity(
                projectId: pid, taskId: task.id, kind: "note", body: text,
                attachmentIds: uploadedIds.isEmpty ? nil : uploadedIds
            )
            newNote = ""
            pendingAttachments = []
            await loadHistory()
        } catch {
            // Best-effort; leave the text in place so the user can retry.
            // Note: attachments were already uploaded and persisted on the
            // task — they show up under ATTACHMENTS even if the activity
            // POST failed.
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

/// One review-cycle round on a kanban task. A new round opens every time
/// the card leaves `review` for a non-done column (sent back for changes,
/// or assignee pulls it out of review). Round 1 covers the initial work
/// from creation up to the first submission for review.
///
/// Events inside a round are kept chronological so the round reads as a
/// story: "moved to In Progress · added subtask · note · moved to Review ·
/// reviewer note · sent back" → next round opens.
struct TaskRound: Identifiable {
    let index: Int
    let events: [MWTaskHistoryEntry]
    let isLatest: Bool

    var id: Int { index }

    /// Highest-signal column the round currently sits in, used in the round
    /// header chip ("Round 3 · In Review", "Round 2 · Sent back"). Derived
    /// from the last column_change in this round; defaults to the task's
    /// starting column for round 1 if no moves happened yet.
    var phaseLabel: String {
        let last = events.reversed().first { $0.eventType == "column_change" }
        let col = last?.toValue ?? "todo"
        switch col {
        case "todo": return "Todo"
        case "in_progress": return "In Progress"
        case "review": return "In Review"
        case "changes_requested": return "Sent Back"
        case "done": return "Done"
        default: return col.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var phaseColor: Color {
        let last = events.reversed().first { $0.eventType == "column_change" }
        switch last?.toValue ?? "" {
        case "review": return .blue
        case "changes_requested": return .orange
        case "done": return .matcha500
        case "in_progress": return .yellow
        default: return .secondary
        }
    }

    /// Build chronological rounds from a flat history list.
    static func build(from history: [MWTaskHistoryEntry]) -> [TaskRound] {
        let sorted = history.sorted { $0.createdAt < $1.createdAt }
        var buckets: [[MWTaskHistoryEntry]] = [[]]
        for e in sorted {
            // A new round opens when the card LEAVES review for any
            // non-done column. The "leaving review" event itself lands at
            // the top of the new round so reviewer-feedback notes flow
            // straight into the assignee's response.
            if e.eventType == "column_change",
               let from = e.fromValue, from == "review",
               let to = e.toValue, to != "done" {
                buckets.append([])
            }
            buckets[buckets.count - 1].append(e)
        }
        // Drop trailing empty bucket if any (defensive — shouldn't happen).
        if buckets.last?.isEmpty == true { buckets.removeLast() }
        if buckets.isEmpty { return [] }
        return buckets.enumerated().map { idx, events in
            TaskRound(index: idx + 1, events: events, isLatest: idx == buckets.count - 1)
        }
    }
}

/// Renders one TaskRound: a header row (Round N · phase chip) plus the
/// round's events. The latest round is always expanded; older rounds are
/// collapsed under a DisclosureGroup so a thrashing ticket doesn't bury
/// the active conversation under audit-log noise.
private struct RoundView: View {
    let round: TaskRound
    let files: [MWProjectFile]
    let onPreview: (MWProjectFile) -> Void

    @State private var isExpanded: Bool

    init(round: TaskRound, files: [MWProjectFile], onPreview: @escaping (MWProjectFile) -> Void) {
        self.round = round
        self.files = files
        self.onPreview = onPreview
        // Latest round starts expanded; older rounds collapsed until
        // explicitly opened.
        self._isExpanded = State(initialValue: round.isLatest)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            DisclosureGroup(isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(round.events) { event in
                        EventRow(event: event, files: files, onPreview: onPreview)
                    }
                }
                .padding(.top, 6)
                .padding(.leading, 4)
            } label: {
                HStack(spacing: 6) {
                    if round.isLatest {
                        // Pulse-eligible "CURRENT" badge on the latest round so
                        // the reader's eye lands here first when reopening a
                        // long-cycled ticket.
                        HStack(spacing: 3) {
                            Circle()
                                .fill(round.phaseColor)
                                .frame(width: 6, height: 6)
                            Text("CURRENT")
                                .font(.system(size: 8, weight: .bold))
                                .foregroundColor(round.phaseColor)
                                .tracking(0.7)
                        }
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(round.phaseColor.opacity(0.18))
                        .cornerRadius(3)
                    }
                    Text("Round \(round.index)")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.white.opacity(0.9))
                    Text("·")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Text(round.phaseLabel)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(round.phaseColor)
                        .tracking(0.5)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(round.phaseColor.opacity(0.15))
                        .cornerRadius(3)
                    Spacer()
                    Text("\(round.events.count) event\(round.events.count == 1 ? "" : "s")")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }
            .accentColor(.secondary)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(round.isLatest ? Color.zinc800.opacity(0.55) : Color.zinc800.opacity(0.3))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(round.isLatest ? round.phaseColor.opacity(0.35) : Color.clear, lineWidth: 1)
        )
        .cornerRadius(6)
    }
}

/// One event inside a round. Dispatches on `event_type` so notes render
/// rich (body + image thumbnails) while structural events render as a
/// single icon + line ("haley added subtask: 'Add EIN validation'").
private struct EventRow: View {
    let event: MWTaskHistoryEntry
    let files: [MWProjectFile]
    let onPreview: (MWProjectFile) -> Void

    var body: some View {
        if event.eventType == "activity" {
            // Notes get the full card treatment (body + actor + thumbs).
            NoteRow(entry: event, files: files, onPreview: onPreview)
        } else {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: Self.icon(for: event.eventType))
                    .font(.system(size: 11))
                    .foregroundColor(Self.tint(for: event.eventType))
                    .frame(width: 14, alignment: .center)
                VStack(alignment: .leading, spacing: 1) {
                    Text(Self.describe(event))
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true)
                    Text(PacificDateFormatter.absolute(event.createdAt) ?? event.createdAt)
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 1)
        }
    }

    private static func icon(for event: String) -> String {
        switch event {
        case "created": return "plus.circle.fill"
        case "column_change": return "arrow.right.circle"
        case "assignee_change": return "person.circle"
        case "description_change": return "text.alignleft"
        case "progress_note_change": return "note.text"
        case "review_rejected": return "arrow.uturn.backward.circle"
        case "subtask_added": return "plus.square"
        case "subtask_completed": return "checkmark.square.fill"
        case "subtask_uncompleted": return "square"
        case "subtask_deleted": return "trash"
        case "deleted": return "trash.circle"
        default: return "circle"
        }
    }

    private static func tint(for event: String) -> Color {
        switch event {
        case "created": return .matcha500
        case "column_change": return .matcha500
        case "assignee_change": return .blue
        case "description_change": return .matcha500
        case "progress_note_change": return .matcha500
        case "review_rejected": return .orange
        case "subtask_added": return .blue
        case "subtask_completed": return .matcha500
        case "subtask_uncompleted": return .orange
        case "subtask_deleted": return .red
        case "deleted": return .red
        default: return .secondary
        }
    }

    private static func describe(_ e: MWTaskHistoryEntry) -> String {
        let who = (e.actorName?.isEmpty == false ? e.actorName! : "Someone")
        switch e.eventType {
        case "created":
            return "\(who) created this task" + (e.toValue.map { " in \(columnLabel($0))" } ?? "")
        case "column_change":
            let from = e.fromValue.map { columnLabel($0) } ?? "?"
            let to = e.toValue.map { columnLabel($0) } ?? "?"
            return "\(who) moved \(from) → \(to)"
        case "assignee_change":
            if e.toValue == nil { return "\(who) unassigned this task" }
            return "\(who) updated the assignee"
        case "description_change":
            return "\(who) updated the description"
        case "progress_note_change":
            return "\(who) updated where we're at"
        case "review_rejected":
            let note = (e.metadata?["note"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return note.isEmpty
                ? "\(who) sent this back for changes"
                : "\(who) sent back: \u{201C}\(note)\u{201D}"
        case "subtask_added":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) added a checklist item"
                : "\(who) added: \u{201C}\(title)\u{201D}"
        case "subtask_completed":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) completed a checklist item"
                : "\(who) completed: \u{201C}\(title)\u{201D}"
        case "subtask_uncompleted":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) reopened a checklist item"
                : "\(who) reopened: \u{201C}\(title)\u{201D}"
        case "subtask_deleted":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) removed a checklist item"
                : "\(who) removed: \u{201C}\(title)\u{201D}"
        case "deleted":
            return "\(who) deleted this task"
        default:
            return "\(who) \(e.eventType)"
        }
    }

    private static func columnLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

/// One pending image/file queued in the note composer before the note
/// is submitted. Held in memory only — uploaded to mw_project_files on
/// submit and linked to the activity row via metadata.attachment_ids.
struct PendingAttachment: Identifiable, Equatable {
    let id = UUID()
    let data: Data
    let filename: String
    let mimeType: String

    var isImage: Bool { mimeType.lowercased().hasPrefix("image/") }
}

/// Chip rendered under the composer for each pending attachment. Click ×
/// to drop one before submitting. Shows a tiny thumbnail for images so
/// the user can confirm they grabbed the right screenshot.
private struct PendingAttachmentChip: View {
    let attachment: PendingAttachment
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 5) {
            if attachment.isImage, let nsImg = NSImage(data: attachment.data) {
                Image(nsImage: nsImg)
                    .resizable()
                    .interpolation(.medium)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 22, height: 22)
                    .clipShape(RoundedRectangle(cornerRadius: 3))
            } else {
                Image(systemName: attachment.isImage ? "photo" : "doc")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Text(attachment.filename)
                .font(.system(size: 10))
                .foregroundColor(.white)
                .lineLimit(1)
                .truncationMode(.middle)
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Remove")
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(Color.zinc800.opacity(0.8))
        .cornerRadius(4)
    }
}

/// One note in the task feed. Renders body + actor/timestamp footer plus
/// (when the note has linked file ids) a row of inline image thumbnails
/// resolved from the task's uploaded files. Tap a thumbnail to open the
/// existing AttachmentPreviewSheet.
private struct NoteRow: View {
    let entry: MWTaskHistoryEntry
    let files: [MWProjectFile]
    let onPreview: (MWProjectFile) -> Void

    private var body_: String {
        (entry.metadata?["body"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var linkedFiles: [MWProjectFile] {
        guard let ids = entry.attachmentIds, !ids.isEmpty else { return [] }
        let idSet = Set(ids)
        return files.filter { idSet.contains($0.id) }
    }

    var body: some View {
        let bodyText = body_
        let linked = linkedFiles
        if bodyText.isEmpty && linked.isEmpty { EmptyView() } else {
            VStack(alignment: .leading, spacing: 4) {
                if !bodyText.isEmpty {
                    Text(bodyText)
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.9))
                        .textSelection(.enabled)
                }
                if !linked.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(linked) { f in
                                NoteAttachmentThumb(file: f) { onPreview(f) }
                            }
                        }
                    }
                }
                Text("\((entry.actorName?.isEmpty == false ? entry.actorName! : "Someone")) · \(PacificDateFormatter.absolute(entry.createdAt) ?? "")")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.zinc800.opacity(0.5))
            .cornerRadius(5)
        }
    }
}

/// Inline thumbnail rendered inside a NoteRow for each linked file.
/// Images load remotely via AsyncImage; non-images fall back to a doc
/// icon + filename chip.
private struct NoteAttachmentThumb: View {
    let file: MWProjectFile
    let onTap: () -> Void

    var body: some View {
        Group {
            if file.isImage, let url = URL(string: file.storageUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable()
                            .interpolation(.medium)
                            .aspectRatio(contentMode: .fill)
                    case .failure:
                        Image(systemName: "photo")
                            .foregroundColor(.secondary)
                    default:
                        ProgressView().controlSize(.small)
                    }
                }
                .frame(width: 92, height: 64)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.zinc800, lineWidth: 1)
                )
            } else {
                HStack(spacing: 4) {
                    Image(systemName: "doc")
                        .font(.system(size: 11))
                    Text(file.filename)
                        .font(.system(size: 10))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color.zinc800)
                .cornerRadius(4)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
        .help(file.filename)
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
