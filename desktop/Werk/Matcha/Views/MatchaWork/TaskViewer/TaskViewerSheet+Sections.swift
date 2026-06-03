import SwiftUI

// MARK: - Section views (state banner, rounds, discussion, attachments, checklist)

extension TaskViewerSheet {
    /// Collapsed stand-in for the rounds + audit History feed (the background).
    /// History is already loaded on open for the Discussion thread, so tapping
    /// just reveals it; the lazy fetch stays as a safety net.
    var historyToggle: some View {
        Button {
            showHistory = true
            if !historyLoaded {
                Task { await loadHistory() }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("HISTORY")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if rounds.count > 1 {
                    Text("\(rounds.count) rounds")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.zinc800)
                        .cornerRadius(4)
                }
                Spacer()
                Text("Show")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.matcha500)
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.matcha500)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity)
            .background(Color.zinc800.opacity(0.4))
            .cornerRadius(6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - In-review audit

    /// Items the reviewer denied this cycle and that are still open: the latest
    /// `subtask_rejected` reason per not-done subtask. Drives the audit list in
    /// the changes-requested (NEEDS WORK) section. `createdAt` is ISO8601, so a
    /// lexical compare is chronological.
    var reviewDenials: [(title: String, reason: String)] {
        let openIds = Set(subtasks.filter { !$0.isDone }.map { $0.id })
        var latest: [String: MWTaskHistoryEntry] = [:]
        for e in history where e.eventType == "subtask_rejected" {
            guard let sid = e.metadata?["subtask_id"], openIds.contains(sid) else { continue }
            if let prev = latest[sid], prev.createdAt >= e.createdAt { continue }
            latest[sid] = e
        }
        return latest.values
            .sorted { $0.createdAt < $1.createdAt }
            .map { (title: $0.metadata?["title"] ?? "Item", reason: $0.metadata?["reason"] ?? "") }
    }

    // MARK: - "You are here" state banner

    struct StatePhase {
        let label: String
        let owner: String
        let color: Color
        let icon: String
    }

    var currentPhase: StatePhase {
        // A ticket sent back from review now lands in `todo` (the active flow)
        // carrying a reviewNote — frame it as rework ("address the feedback"),
        // not a cold never-started task.
        let hasFeedback = (task.reviewNote?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false)
        if task.boardColumn == "todo" && hasFeedback {
            return StatePhase(label: "Changes Requested", owner: "Assignee to address feedback", color: .orange, icon: "arrow.uturn.backward.circle.fill")
        }
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
    var stateBanner: some View {
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
            // Round number comes from the subtasks (currentRound), not the
            // history feed — so it shows the moment the ticket opens, without
            // forcing the now-lazy history fetch.
            if currentRound > 0 {
                Text("Round \(currentRound)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(p.color)
            }
        }
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        // Color lives in the text/icon, not a filled banner. A hairline keeps
        // the status separated from the body without another tinted box.
        .overlay(
            Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.06)),
            alignment: .bottom
        )
    }

    // MARK: - Rounds (foreground latest-update card)

    /// The latest round rendered inline in the foreground — surfaces the current
    /// changes-requested + "fixed in round N-1" so the user doesn't have to
    /// expand History to see what changed. Multi-round tickets only.
    @ViewBuilder
    var currentRoundCard: some View {
        if rounds.count > 1, let current = rounds.last {
            VStack(alignment: .leading, spacing: 6) {
                Text("LATEST UPDATE · ROUND \(current.index)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.matcha500)
                    .tracking(0.5)
                RoundView(
                    round: current,
                    previousFixed: rounds[rounds.count - 2].fixedSubtaskTitles,
                    files: attachments,
                    onPreview: { previewFile = $0 }
                )
            }
        }
    }

    /// Small "Round N" chip marking a foreground section as scoped to the live
    /// round, so it's explicit the body is showing the current round's work.
    var roundScopePill: some View {
        Text("Round \(currentRound)")
            .font(.system(size: 8, weight: .semibold))
            .foregroundColor(.matcha500)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(Color.matcha500.opacity(0.15))
            .cornerRadius(4)
    }

    // MARK: - History (rounds-grouped audit) + Discussion (notes thread)

    /// The in-ticket Q&A thread: a note composer plus the activity notes,
    /// newest-first. Always visible in every column so clarifying questions
    /// are one click away. Posting a note bells the other participants.
    @ViewBuilder
    var discussionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
                Text("DISCUSSION")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                Text("Ask & answer clarifications")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.7))
                if loadingHistory {
                    ProgressView().controlSize(.small)
                }
                Spacer()
                if currentRound > 1 {
                    roundScopePill
                }
            }

            noteComposer

            // One combined thread, newest-first (current-round comments land on
            // top). Each row carries a Round-N chip and prior-round comments are
            // dimmed, so it's never ambiguous which round a comment is from.
            if !notes.isEmpty {
                ForEach(Array(notes.reversed())) { note in
                    NoteRow(
                        entry: note,
                        files: attachments,
                        noteRound: roundIndex(forCreatedAt: note.createdAt),
                        currentRound: currentRound,
                        onPreview: { previewFile = $0 },
                        onReply: {
                            replyingToNote = note
                            isNoteFieldFocused = true
                        }
                    )
                }
            } else if !loadingHistory {
                Text("No comments yet — ask a question to start the thread.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .padding(.vertical, 4)
            }
        }
    }

    /// The background: structural rounds + audit trail. Collapsed by default
    /// (toggled via `historyToggle`). Prior rounds carry their fixed items and
    /// older attachments out of the foreground. Hosts "Start Next Round".
    @ViewBuilder
    var historySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("HISTORY")
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
                if loadingHistory {
                    ProgressView().controlSize(.small)
                }
                Spacer()
                Button { showHistory = false } label: {
                    Image(systemName: "chevron.up")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Collapse history")
                Button {
                    showingNewRoundSheet = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "plus.circle.fill")
                            .font(.system(size: 10))
                        Text("Start Next Round")
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .foregroundColor(.matcha500)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.matcha500.opacity(0.12))
                    .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .help("Open a new round with a suggested-fix subtask. Any collaborator can start one.")
            }

            // Rounds rendered newest-first so the active round sits on top.
            // Within each round events stay chronological (oldest → newest).
            // `previousFixed` threads the prior round's completed subtask
            // titles forward so round N+1 shows "Fixed in Round N · …".
            // The current round is surfaced inline (currentRoundCard), so History
            // keeps the prior rounds only — no duplication.
            let historyRounds = rounds.count > 1 ? Array(rounds.dropLast()) : rounds
            let reversed = Array(historyRounds.reversed())
            ForEach(Array(reversed.enumerated()), id: \.element.id) { idx, round in
                // `reversed` is newest-first; the round AFTER this one in
                // chronological time is the previous element in `reversed`
                // (idx-1). For the latest round (idx 0) there's no "next."
                // The summary block belongs ON round N+1, so we look at
                // round N = reversed[idx+1] when rendering reversed[idx].
                let previousIndex = idx + 1
                let previousFixed: [String] = (previousIndex < reversed.count)
                    ? reversed[previousIndex].fixedSubtaskTitles
                    : []
                RoundView(
                    round: round,
                    previousFixed: round.index >= 2 ? previousFixed : [],
                    files: attachments,
                    onPreview: { previewFile = $0 }
                )
            }
        }
    }

    @ViewBuilder
    var noteComposer: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let replying = replyingToNote {
                replyingToBanner(replying)
            }
            HStack(spacing: 6) {
                TextField(replyingToNote == nil ? "Add a note…" : "Write a reply…", text: $newNote)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .padding(7)
                    .background(Color.zinc800.opacity(0.6))
                    .cornerRadius(5)
                    .focused($isNoteFieldFocused)
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

    /// "Replying to {name}: {excerpt}" chip shown above the composer while a
    /// reply is in flight. Tapping the × clears the reply target.
    @ViewBuilder
    func replyingToBanner(_ note: MWTaskHistoryEntry) -> some View {
        let name = note.actorName?.isEmpty == false ? note.actorName! : "comment"
        let excerpt = (note.metadata?["body"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\n", with: " ")
        HStack(spacing: 6) {
            Rectangle()
                .fill(Color.matcha500)
                .frame(width: 2)
                .cornerRadius(1)
            VStack(alignment: .leading, spacing: 1) {
                Text("Replying to \(name)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.matcha500)
                if !excerpt.isEmpty {
                    Text(excerpt)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            Button {
                replyingToNote = nil
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Cancel reply")
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 5)
        .background(Color.zinc800.opacity(0.4))
        .cornerRadius(5)
    }

    var canSubmitNote: Bool {
        let hasText = !newNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return hasText || !pendingAttachments.isEmpty
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
                    .background(Color.zinc800)
                    .cornerRadius(4)
                if currentRound > 1 {
                    Text("Round \(currentRound)")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                }
            }
            // Foreground: only this round's files.
            VStack(spacing: 3) {
                ForEach(currentRoundAttachments) { f in
                    ViewerAttachmentRow(file: f) {
                        previewFile = f
                    }
                }
            }
            if currentRoundAttachments.isEmpty {
                Text("No files this round.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }

            // Background: earlier rounds' files behind a disclosure so they
            // stay reachable without cluttering the active round.
            if !earlierRoundAttachments.isEmpty {
                Button {
                    withAnimation { showEarlierAttachments.toggle() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: showEarlierAttachments ? "chevron.down" : "chevron.right")
                            .font(.system(size: 8, weight: .semibold))
                        Text("\(earlierRoundAttachments.count) from earlier round\(earlierRoundAttachments.count == 1 ? "" : "s")")
                            .font(.system(size: 9, weight: .semibold))
                    }
                    .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                if showEarlierAttachments {
                    VStack(spacing: 3) {
                        ForEach(earlierRoundAttachments) { f in
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
                Spacer()
                if currentRound > 1 {
                    roundScopePill
                }
            }

            ForEach(subtasks) { item in
                VStack(alignment: .leading, spacing: 3) {
                    SubtaskRow(
                        item: item,
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
                        onDeny: { reason in
                            Task { await viewModel.denySubtask(taskId: task.id, subtaskId: item.id, reason: reason) }
                        }
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
                            Image(systemName: "sparkles").font(.system(size: 8)).foregroundColor(.purple)
                            Text("Completed by commit \(comp.commitShortSha ?? "?") · \(Int((comp.confidence * 100).rounded()))%"
                                 + (comp.reasoning.map { " — \($0)" } ?? ""))
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.55))
                                .lineLimit(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.leading, 22)
                        .help("This item was checked off by the commit scanner — ✗ deny it above if the work isn't actually complete.")
                    }
                }
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

    // MARK: - Reviewer send-back

    @ViewBuilder
    var rejectEditor: some View {
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
}
