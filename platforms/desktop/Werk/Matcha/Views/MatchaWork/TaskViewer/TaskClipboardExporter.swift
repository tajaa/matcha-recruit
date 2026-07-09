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
///
/// A ticket sent back from review is the exception: there the review IS the
/// content. Pass a `ReviewContext` and the blob is reshaped into a rework brief
/// — the directive and the rejection lead, the original ticket demotes to
/// supporting context. Without one, the output is byte-identical to before.
enum TaskClipboardExporter {

    /// One checklist item the reviewer rejected, with why and how badly. Comes
    /// from a `subtask_rejected` history event's metadata, not from the subtask
    /// row — reason and severity are stored nowhere else.
    struct Denial {
        let title: String
        let reason: String
        let severity: String
    }

    /// What a coding agent needs in order to understand the ticket is a REWORK:
    /// what the reviewer rejected, where in the review cycle we are, and which
    /// work earlier rounds already landed (so it isn't proposed again).
    /// Built by `TaskViewerSheet.reviewContext`; nil for a never-rejected ticket.
    struct ReviewContext {
        let note: String
        let denials: [Denial]
        /// "2 blockers · 1 nit", or nil when no denial carried a severity.
        let severitySummary: String?
        let currentRound: Int
        let totalRounds: Int
        /// Times this ticket has been sent back. 0 when the server didn't say.
        let cycleCount: Int
        let sentBackBy: String?
        /// ISO8601 timestamp of the latest `review_rejected` event.
        let sentBackAt: String?
        /// Titles completed in each earlier round, oldest round first.
        let fixedEarlier: [(round: Int, titles: [String])]
    }

    static func markdown(
        for task: MWProjectTask,
        attachments: [MWProjectFile],
        subtasks: [MWSubtask] = [],
        screenshotPaths: [String] = [],
        review: ReviewContext? = nil,
    ) -> String {
        var lines: [String] = []
        lines.append("# \(task.title)")
        lines.append("")

        if let review {
            appendRework(review, subtasks: subtasks, to: &lines)
        }

        // On a rework the brief is context, not the ask — retitle it and let the
        // changes requested sit above it.
        lines.append(review == nil ? "## Description" : "## The brief (original ticket)")
        let description = (task.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        lines.append(description.isEmpty ? "_(no description)_" : description)
        lines.append("")

        lines.append("## Where We're At")
        let progress = (task.progressNote ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        lines.append(progress.isEmpty ? "_(no progress note)_" : progress)
        lines.append("")

        // The rework path already printed the checklist, scoped to its round.
        if !subtasks.isEmpty && review == nil {
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

    /// The rework header: a directive naming this as a send-back, the reviewer's
    /// note and rejected items, this round's checklist, and a compressed list of
    /// what earlier rounds already fixed. All of it precedes the original brief.
    private static func appendRework(
        _ review: ReviewContext,
        subtasks: [MWSubtask],
        to lines: inout [String],
    ) {
        let round = review.totalRounds > 1
            ? "You are on round \(review.currentRound) of \(review.totalRounds). "
            : ""
        let dontRedo = review.fixedEarlier.isEmpty
            ? ""
            : " Do not re-do items listed under \"Already fixed\"."
        lines.append("> **Task for you:** This ticket was reviewed and sent back for changes. "
                     + round
                     + "Address the changes requested below. The original brief and earlier rounds "
                     + "are context, not new work." + dontRedo)
        lines.append("")

        lines.append("## Changes requested")
        if let attribution = attributionLine(review) {
            lines.append(attribution)
            lines.append("")
        }
        // Blockquote the reviewer's own words so a multi-line note can't be read
        // as part of the surrounding instructions.
        for line in review.note.split(separator: "\n", omittingEmptySubsequences: false) {
            lines.append("> \(line)")
        }
        lines.append("")

        for d in review.denials {
            let tag = d.severity.isEmpty ? "" : "**[\(d.severity)]** "
            let reason = d.reason.isEmpty ? "" : " — \(d.reason)"
            lines.append("- \(tag)\(d.title)\(reason)")
        }
        if !review.denials.isEmpty { lines.append("") }

        if !subtasks.isEmpty {
            let done = subtasks.filter { $0.isDone }.count
            lines.append("## Open checklist (round \(review.currentRound), \(done)/\(subtasks.count) done)")
            for s in subtasks.sorted(by: { $0.position < $1.position }) {
                lines.append("- [\(s.isDone ? "x" : " ")] \(s.title)")
            }
            lines.append("")
        }

        if !review.fixedEarlier.isEmpty {
            lines.append("## Already fixed in earlier rounds")
            for round in review.fixedEarlier {
                for title in round.titles {
                    lines.append("- Round \(round.round): \(title)")
                }
            }
            lines.append("")
        }
    }

    /// "Sent back by Jane Doe on Jul 7, 2026 (3rd send-back) — 2 blockers · 1 nit".
    /// Every clause is optional; nil when none of them are known, since a bare
    /// "Sent back" says nothing the directive above hasn't already said.
    private static func attributionLine(_ review: ReviewContext) -> String? {
        var head = "Sent back"
        var known = false
        if let who = review.sentBackBy, !who.isEmpty { head += " by \(who)"; known = true }
        if let at = review.sentBackAt, let when = PacificDateFormatter.absolute(at) {
            head += " on \(when)"
            known = true
        }
        // "1st send-back" is just "sent back" — only worth saying once it repeats.
        if review.cycleCount > 1 { head += " (\(ordinal(review.cycleCount)) send-back)"; known = true }
        if let severity = review.severitySummary { head += " — \(severity)"; known = true }
        return known ? head : nil
    }

    private static func ordinal(_ n: Int) -> String {
        switch n % 100 {
        case 11, 12, 13: return "\(n)th"
        default:
            switch n % 10 {
            case 1: return "\(n)st"
            case 2: return "\(n)nd"
            case 3: return "\(n)rd"
            default: return "\(n)th"
            }
        }
    }

    private static func formatSize(_ bytes: Int) -> String {
        let b = Double(bytes)
        if b < 1024 { return "\(bytes) B" }
        if b < 1024 * 1024 { return String(format: "%.1f KB", b / 1024) }
        return String(format: "%.1f MB", b / 1024 / 1024)
    }
}
