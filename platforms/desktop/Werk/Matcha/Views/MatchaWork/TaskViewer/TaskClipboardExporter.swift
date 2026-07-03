import Foundation

/// Builds a clipboard-friendly markdown blob describing a task. Used by
/// TaskViewerSheet's Copy button so the user can drop the ticket into Claude
/// Code / Codex / any chat that accepts markdown. Deliberately content-only
/// (title, description, progress, checklist, attachments, screenshots) — the
/// project-management metadata (status, priority, assignee, due date) is
/// omitted because it's noise to a coding agent acting on the ticket.
/// Screenshots are referenced by LOCAL file path (`screenshotPaths`) so Claude
/// Code can open them with its Read tool — not by CloudFront URL, which CLIs
/// can't fetch.
enum TaskClipboardExporter {
    static func markdown(
        for task: MWProjectTask,
        attachments: [MWProjectFile],
        subtasks: [MWSubtask] = [],
        screenshotPaths: [String] = [],
    ) -> String {
        var lines: [String] = []
        lines.append("# \(task.title)")
        lines.append("")

        lines.append("## Description")
        let description = (task.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        lines.append(description.isEmpty ? "_(no description)_" : description)
        lines.append("")

        lines.append("## Where We're At")
        let progress = (task.progressNote ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        lines.append(progress.isEmpty ? "_(no progress note)_" : progress)
        lines.append("")

        if !subtasks.isEmpty {
            let done = subtasks.filter { $0.isDone }.count
            lines.append("## Checklist (\(done)/\(subtasks.count))")
            for s in subtasks.sorted(by: { $0.position < $1.position }) {
                lines.append("- [\(s.isDone ? "x" : " ")] \(s.title)")
            }
            lines.append("")
        }

        // Non-image attachments by name only — the CloudFront URLs are dead
        // weight to a CLI, and listing them was the "directories" noise.
        let nonImages = attachments.filter { !$0.isImage }
        if !nonImages.isEmpty {
            lines.append("## Attachments (\(nonImages.count))")
            for f in nonImages {
                lines.append("- \(f.filename) — \(formatSize(f.fileSize))")
            }
            lines.append("")
        }

        // Screenshots as LOCAL paths Claude Code can open directly.
        if !screenshotPaths.isEmpty {
            lines.append("## Screenshots")
            lines.append("_Local files — open these to view:_")
            for p in screenshotPaths {
                lines.append(p)
            }
            lines.append("")
        }

        return lines.joined(separator: "\n")
    }

    private static func formatSize(_ bytes: Int) -> String {
        let b = Double(bytes)
        if b < 1024 { return "\(bytes) B" }
        if b < 1024 * 1024 { return String(format: "%.1f KB", b / 1024) }
        return String(format: "%.1f MB", b / 1024 / 1024)
    }
}
