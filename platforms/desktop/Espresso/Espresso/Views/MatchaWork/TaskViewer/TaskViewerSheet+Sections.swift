import SwiftUI

// MARK: - Foreground work sections: attachments + checklist
//
// The rest of the sheet's sections live in siblings of this file, split by the
// question each one answers:
//   • TaskViewerSheet+Header.swift     — phase, meta line, the directive hero
//   • TaskViewerSheet+Review.swift     — denials, round delta, send-back editor
//   • TaskViewerSheet+History.swift    — collapsibles + the rounds/audit feed
//   • TaskViewerSheet+Discussion.swift — the Q&A thread and its composer

extension TaskViewerSheet {

    // MARK: - Research deliverable

    /// Research is a first-class card result, not just another attachment.
    /// The existing attachment preview already renders Markdown (with a
    /// Rendered/Source toggle) and PDF; this row makes that reader discoverable
    /// next to the card's current state.
    @ViewBuilder
    var researchReportSection: some View {
        if liveAutoPRTask.category == "research" {
            if let report = researchReportAttachment {
                Button { previewFile = report } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "doc.text.magnifyingglass")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundColor(.mwInkStrong)
                            .frame(width: 28, height: 28)
                            .background(Color.mwInkStrong.opacity(0.12))
                            .cornerRadius(6)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("RESEARCH REPORT")
                                .font(.system(size: 9, weight: .bold))
                                .tracking(0.5)
                                .foregroundColor(.mwInkStrong)
                            Text(report.filename)
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeTextSecondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        Spacer(minLength: 0)
                        Text("Read report")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.mwInkStrong)
                        Image(systemName: "arrow.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.mwInkStrong)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.mwInkStrong.opacity(0.06))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.mwInkStrong.opacity(0.18), lineWidth: 1)
                    )
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else if liveAutoPRTask.autoprClaimedAt != nil
                        || liveAutoPRTask.isAutoPRQueueCandidate {
                Label("Research report will appear here when the run finishes.",
                      systemImage: "doc.text.magnifyingglass")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
    }

    // MARK: - Attachments (task-level files)

    @ViewBuilder
    var attachmentsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "paperclip")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("ATTACHMENTS")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                Text("\(currentRoundAttachments.count)")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(appState.themeText.opacity(0.08))
                    .cornerRadius(4)
                if currentRound > 1 {
                    Text("Round \(currentRound)")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                }
            }
            // Foreground: only this round's files.
            let thisRound = currentRoundAttachments
            VStack(spacing: 3) {
                ForEach(thisRound) { f in
                    ViewerAttachmentRow(file: f) {
                        previewFile = f
                    }
                }
            }
            if thisRound.isEmpty {
                Text("No files this round.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }

            // Background: earlier rounds' files behind a disclosure so they
            // stay reachable without cluttering the active round.
            let earlier = earlierRoundAttachments
            if !earlier.isEmpty {
                Button {
                    withAnimation { showEarlierAttachments.toggle() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: showEarlierAttachments ? "chevron.down" : "chevron.right")
                            .font(.system(size: 8, weight: .semibold))
                        Text("\(earlier.count) from earlier round\(earlier.count == 1 ? "" : "s")")
                            .font(.system(size: 9, weight: .semibold))
                    }
                    .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                if showEarlierAttachments {
                    VStack(spacing: 3) {
                        ForEach(earlier) { f in
                            ViewerAttachmentRow(file: f) {
                                previewFile = f
                            }
                            .opacity(0.7)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Checklist (subtasks)

    @ViewBuilder
    var checklistSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            checklistHeader

            ForEach(subtasks) { item in
                checklistRow(item)
            }

            HStack(spacing: 6) {
                TextField("Add a checklist item…", text: $newSubtask)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .padding(7)
                    .background(appState.themeText.opacity(0.07))
                    .cornerRadius(5)
                    .onSubmit { submitSubtask() }
                Button {
                    submitSubtask()
                } label: {
                    if addingSubtask {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Add").font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.mwInkStrong)
                    }
                }
                .buttonStyle(.plain)
                .disabled(addingSubtask || newSubtask.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }

    @ViewBuilder
    private var checklistHeader: some View {
        if appState.isGraphite {
            HStack(spacing: 8) {
                asciiRule(subtasks.isEmpty ? "CHECKLIST" : "CHECKLIST · \(subtaskDoneCount)/\(subtasks.count)")
                if currentRound > 1 { roundScopePill }
            }
        } else {
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
                        .background(appState.themeText.opacity(0.08))
                        .cornerRadius(4)
                }
                Spacer()
                if currentRound > 1 {
                    roundScopePill
                }
            }
        }
    }

    /// One checklist item plus the two AI affordances that hang off it: the
    /// commit-driven completion suggestions (open items) and the commit audit
    /// line the reviewer judges an auto-check by (done items, in review).
    @ViewBuilder
    private func checklistRow(_ item: MWSubtask) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            SubtaskRow(
                item: item,
                taskTitle: task.title,
                collaborators: viewModel.collaborators,
                currentUserId: appState.currentUser?.id,
                onToggle: {
                    Task { await viewModel.toggleSubtask(taskId: task.id, subtaskId: item.id, isDone: !item.isDone) }
                },
                onDelete: {
                    Task { await viewModel.deleteSubtask(taskId: task.id, subtaskId: item.id) }
                },
                onAssign: { newAssignee in
                    Task { await viewModel.assignSubtask(taskId: task.id, subtaskId: item.id, assignedTo: newAssignee) }
                },
                // In review, the reviewer can deny a completed item.
                canReview: task.boardColumn == "review",
                onDeny: { reason, severity in
                    Task { await viewModel.denySubtask(taskId: task.id, subtaskId: item.id, reason: reason, severity: severity) }
                },
                addedByName: addedByReviewerName(item)
            )
            // Commit-driven completion suggestions — only for items not
            // yet checked (a done item needs no suggestion).
            if !item.isDone {
                ForEach(viewModel.suggestions(taskId: task.id, subtaskId: item.id)) { sug in
                    CommitSuggestionChip(
                        suggestion: sug,
                        onAccept: { Task { await viewModel.acceptSuggestion(sug) } },
                        onDismiss: { Task { await viewModel.dismissSuggestion(sug) } }
                    )
                    .padding(.leading, 22)
                }
            }
            // In review: audit which commit completed a done item, so the
            // reviewer can judge (and ✗-deny) the AI auto-check.
            if task.boardColumn == "review", item.isDone,
               let comp = viewModel.completion(subtaskId: item.id) {
                HStack(alignment: .top, spacing: 5) {
                    Image(systemName: "sparkles").font(.system(size: 8)).foregroundColor(.mwInkSoft)
                    Text("Completed by commit \(comp.commitShortSha ?? "?") · \(Int((comp.confidence * 100).rounded()))%"
                         + (comp.reasoning.map { " — \($0)" } ?? ""))
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeText.opacity(0.55))
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.leading, 22)
                .help("This item was checked off by the commit scanner — ✗ deny it above if the work isn't actually complete.")
            }
        }
    }
}
