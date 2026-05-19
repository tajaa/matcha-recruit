import SwiftUI
import AppKit

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

    private var attachments: [MWProjectFile] {
        viewModel.taskFiles[task.id] ?? []
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
                Button(action: copyTicketToClipboard) {
                    Image(systemName: didCopy ? "checkmark" : "doc.on.doc")
                        .font(.system(size: 11))
                        .foregroundColor(didCopy ? .matcha500 : .secondary)
                }
                .buttonStyle(.plain)
                .help("Copy ticket as markdown")
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
                Spacer()
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

            if !history.isEmpty {
                TaskHistoryTimeline(entries: history)
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

            HStack {
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

    private func copyTicketToClipboard() {
        let markdown = TaskClipboardExporter.markdown(
            for: task,
            assigneeName: assigneeName,
            columnLabel: columnLabel,
            attachments: attachments,
            history: history,
        )
        let board = NSPasteboard.general
        board.clearContents()
        board.setString(markdown, forType: .string)
        didCopy = true
        Task {
            try? await Task.sleep(for: .milliseconds(1500))
            await MainActor.run { didCopy = false }
        }
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
        history: [MWTaskHistoryEntry],
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

        if !history.isEmpty {
            lines.append("## History")
            for e in history {
                let when = formatHistoryDate(e.createdAt)
                let who = (e.actorName?.isEmpty == false ? e.actorName! : "Someone")
                let action = describeEvent(e)
                lines.append("- \(when) · \(who) · \(action)")
            }
            lines.append("")
        }

        return lines.joined(separator: "\n")
    }

    private static func describeEvent(_ e: MWTaskHistoryEntry) -> String {
        switch e.eventType {
        case "created":
            return "created task" + (e.toValue.map { " in \(columnLabel($0))" } ?? "")
        case "column_change":
            let from = e.fromValue.map { columnLabel($0) } ?? "?"
            let to = e.toValue.map { columnLabel($0) } ?? "?"
            return "moved \(from) → \(to)"
        case "assignee_change":
            return e.toValue == nil ? "unassigned task" : "updated assignee"
        case "description_change":
            return "updated description"
        case "progress_note_change":
            return "updated where we're at"
        case "deleted":
            return "deleted task"
        default:
            return e.eventType
        }
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

    private static func formatHistoryDate(_ iso: String) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date: Date? = f.date(from: iso) ?? {
            f.formatOptions = [.withInternetDateTime]
            return f.date(from: iso)
        }()
        guard let d = date else { return iso }
        let out = DateFormatter()
        out.dateFormat = "yyyy-MM-dd HH:mm"
        return out.string(from: d)
    }
}
