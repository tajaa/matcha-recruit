import SwiftUI

// MARK: - Review: denials, round delta, clipboard context, send-back editor
//
// Split out of TaskViewerSheet+Sections.swift. Everything the *reviewer* side of
// the loop reads or writes lives here.

extension TaskViewerSheet {

    // MARK: - In-review audit

    /// Items the reviewer denied this cycle and that are still open: the latest
    /// `subtask_rejected` reason + severity per not-done subtask. Drives the audit
    /// list in the changes-requested (NEEDS WORK) section. `createdAt` is ISO8601,
    /// so a lexical compare is chronological.
    var reviewDenials: [(title: String, reason: String, severity: String)] {
        let openIds = Set(subtasks.filter { !$0.isDone }.map { $0.id })
        var latest: [String: MWTaskHistoryEntry] = [:]
        for e in history where e.eventType == "subtask_rejected" {
            guard let sid = e.metadata?["subtask_id"], openIds.contains(sid) else { continue }
            if let prev = latest[sid], prev.createdAt >= e.createdAt { continue }
            latest[sid] = e
        }
        return latest.values
            .sorted { $0.createdAt < $1.createdAt }
            .map { (title: $0.metadata?["title"] ?? "Item",
                    reason: $0.metadata?["reason"] ?? "",
                    severity: $0.metadata?["severity"] ?? "") }
    }

    /// "N blocker(s) · M nit(s)" for a denial list, or nil when no severities.
    /// Takes the list so callers that already computed `reviewDenials` (which
    /// walks the whole history) don't pay for it again.
    func denialSeveritySummary(_ denials: [(title: String, reason: String, severity: String)]) -> String? {
        var b = 0, n = 0
        for d in denials {
            if d.severity == "blocker" { b += 1 } else if d.severity == "nit" { n += 1 }
        }
        guard b > 0 || n > 0 else { return nil }
        var parts: [String] = []
        if b > 0 { parts.append("\(b) blocker\(b == 1 ? "" : "s")") }
        if n > 0 { parts.append("\(n) nit\(n == 1 ? "" : "s")") }
        return parts.joined(separator: " · ")
    }

    /// Convenience over `denialSeveritySummary` for callers with no list in hand.
    var denialSeverityCounts: String? { denialSeveritySummary(reviewDenials) }

    // MARK: - Clipboard export context

    /// The review state a copied ticket needs so a coding agent reads it as a
    /// REWORK rather than a fresh feature request. Nil when the ticket carries
    /// no reviewer feedback — the copy then keeps its plain shape.
    ///
    /// The gate is the shared `.feedback` directive, and deliberately isn't
    /// `boardColumn == "changes_requested"`: `reject_project_task` lands the card
    /// there, but `review_note` survives the assignee dragging it to In Progress
    /// to start the rework — which is precisely when they'd copy it. The server
    /// clears the note on re-entry to review/done, so its presence is the truth.
    var reviewContext: TaskClipboardExporter.ReviewContext? {
        guard case .feedback(let note) = directive else { return nil }

        let sentBack = history.last { $0.eventType == "review_rejected" }
        let allRounds = rounds
        let denials = reviewDenials

        // Everything closed before the current round: work the reviewer already
        // accepted. Listing it is what stops the agent rebuilding it.
        let fixedEarlier = allRounds
            .filter { $0.index < currentRound }
            .map { (round: $0.index, titles: $0.fixedSubtaskTitles) }
            .filter { !$0.titles.isEmpty }

        return TaskClipboardExporter.ReviewContext(
            note: note,
            denials: denials.map {
                TaskClipboardExporter.Denial(title: $0.title, reason: $0.reason, severity: $0.severity)
            },
            severitySummary: denialSeveritySummary(denials),
            currentRound: currentRound,
            totalRounds: max(allRounds.count, currentRound),
            cycleCount: task.reviewCycleCount ?? 0,
            sentBackBy: sentBack?.actorName,
            sentBackAt: sentBack?.createdAt,
            fixedEarlier: fixedEarlier,
        )
    }

    // MARK: - Reviewer-added scope (#7)

    /// Name to tag a checklist item with when someone OTHER than the assignee
    /// added it in the current round (new scope, usually the reviewer). Nil when
    /// the item is the assignee's own / from an earlier round / no assignee.
    func addedByReviewerName(_ item: MWSubtask) -> String? {
        guard let assignee = task.assignedTo,
              let by = item.createdBy, by != assignee,
              item.roundIndex == currentRound else { return nil }
        return viewModel.collaborators.first(where: { $0.userId == by })?.name
    }

    // MARK: - Review delta (#5)

    /// What changed in the current round — only meaningful on a re-review
    /// (currentRound > 1). All derived from already-loaded state.
    var reviewDelta: (completed: [String], comments: Int, commits: [String]) {
        var completed: [String] = []
        var comments = 0
        // One pass over history instead of two filters. The event-type check
        // stays first so `roundIndex(forCreatedAt:)` — the expensive part — is
        // still only run for the two types that can contribute.
        for e in history {
            switch e.eventType {
            case "subtask_completed":
                if roundIndex(forCreatedAt: e.createdAt) == currentRound,
                   let t = e.metadata?["title"] { completed.append(t) }
            case "activity":
                if roundIndex(forCreatedAt: e.createdAt) == currentRound { comments += 1 }
            default:
                break
            }
        }
        let commits = viewModel.commitCompletions.values
            .filter { roundIndex(forCreatedAt: $0.createdAt) == currentRound }
            .compactMap { $0.commitShortSha }
        return (completed, comments, Array(Set(commits)).sorted())
    }

    /// "Since last review" — surfaces the round's deltas at the top so a reviewer
    /// re-reviews only what changed. Shown in review when currentRound > 1.
    @ViewBuilder
    var reviewDeltaSection: some View {
        let d = reviewDelta
        if task.boardColumn == "review", currentRound > 1,
           !d.completed.isEmpty || d.comments > 0 || !d.commits.isEmpty {
            HStack(alignment: .top, spacing: 8) {
                RoundedRectangle(cornerRadius: 1).fill(Color.mwInkStrong.opacity(0.7)).frame(width: 2)
                VStack(alignment: .leading, spacing: 3) {
                    Text("SINCE LAST REVIEW")
                        .font(.system(size: 9, weight: .semibold)).tracking(0.5)
                        .foregroundColor(.mwInkStrong)
                    ForEach(d.completed.prefix(6), id: \.self) { t in
                        HStack(spacing: 5) {
                            Image(systemName: "checkmark.circle.fill").font(.system(size: 8)).foregroundColor(.mwInkStrong)
                            Text(t).font(.system(size: 11)).foregroundColor(appState.themeText.opacity(0.8)).lineLimit(1)
                        }
                    }
                    HStack(spacing: 10) {
                        if d.comments > 0 {
                            Label("\(d.comments) new comment\(d.comments == 1 ? "" : "s")", systemImage: "bubble.left")
                                .font(.system(size: 10)).foregroundColor(.secondary)
                        }
                        if !d.commits.isEmpty {
                            Label(d.commits.joined(separator: ", "), systemImage: "arrow.triangle.branch")
                                .font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
                        }
                    }
                }
            }
            .padding(.vertical, 2)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Reviewer send-back

    @ViewBuilder
    var rejectEditor: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("WHAT'S INCOMPLETE?")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(.mwAttention)
                .tracking(0.5)
            TextEditor(text: $rejectNote)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText.opacity(0.9))
                .scrollContentBackground(.hidden)
                .padding(5)
                .frame(height: 64)
                .background(appState.themeText.opacity(0.07))
                .cornerRadius(5)

            // Re-open specific checklist items as part of sending back, so the
            // assignee knows exactly which pieces need rework. Only completed
            // items are candidates; tapping flips them back to not-done live.
            let doneItems = subtasks.filter { $0.isDone }
            if !doneItems.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("RE-OPEN ITEMS")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.mwAttention)
                        .tracking(0.5)
                    ForEach(doneItems) { item in
                        Button {
                            Task { await viewModel.toggleSubtask(taskId: task.id, subtaskId: item.id, isDone: false) }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 11))
                                    .foregroundColor(.mwInkStrong)
                                Text(item.title)
                                    .font(.system(size: 11))
                                    .foregroundColor(appState.themeText.opacity(0.85))
                                    .strikethrough()
                                    .lineLimit(1)
                                Spacer()
                                Text("Re-open")
                                    .font(.system(size: 9, weight: .semibold))
                                    .foregroundColor(.mwAttention)
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
                            .foregroundColor(.mwAttention)
                    }
                }
                .buttonStyle(.plain)
                .disabled(submitting || rejectNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(10)
        .background(Color.mwAttention.opacity(0.08))
        .cornerRadius(6)
    }
}
