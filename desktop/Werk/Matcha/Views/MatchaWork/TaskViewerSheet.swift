import SwiftUI

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

    private var attachments: [MWProjectFile] {
        viewModel.taskFiles[task.id] ?? []
    }

    private var assigneeName: String? {
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
        }
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
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
