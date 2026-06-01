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
    @Environment(AppState.self) private var appState

    @State private var previewFile: MWProjectFile?
    @State private var history: [MWTaskHistoryEntry] = []
    /// Discussion (the in-ticket Q&A thread) is always visible and renders the
    /// activity notes, so history is fetched once on open. `historyLoaded`
    /// guards that one-time fetch; the rounds/audit feed stays collapsed behind
    /// `showHistory` so the audit trail is opt-in, not in the way.
    @State private var showHistory = false
    /// UPDATES log is collapsed by default — it's a read-only audit trail (like
    /// a commit history) for spotting discrepancies, never auto-expanded on open.
    @State private var showUpdates = false
    @State private var historyLoaded = false
    @State private var loadingHistory = false
    /// Earlier-round attachments tuck behind a disclosure so the foreground
    /// ATTACHMENTS list shows only the current round's files.
    @State private var showEarlierAttachments = false
    @State private var didCopy = false
    @State private var isCopying = false
    @State private var newNote = ""
    @State private var addingNote = false
    @FocusState private var isNoteFieldFocused: Bool
    /// The discussion comment the composer is currently replying to, if any.
    /// Drives the "Replying to …" banner and threads `reply_to` through submit.
    @State private var replyingToNote: MWTaskHistoryEntry?
    @State private var isRejecting = false
    @State private var rejectNote = ""
    @State private var submitting = false
    @State private var newSubtask = ""
    @State private var addingSubtask = false
    /// Pending image attachments queued for the next note submit. Cleared
    /// after a successful submit. Each entry is held in-memory until upload.
    @State private var pendingAttachments: [PendingAttachment] = []
    /// Open-state for the "Start Next Round" sheet. Sheet is hosted at the
    /// root of TaskViewerSheet so it lives above all section content.
    @State private var showingNewRoundSheet = false

    private var attachments: [MWProjectFile] {
        viewModel.taskFiles[task.id] ?? []
    }

    /// Foreground attachments — the current round's files. Files with no
    /// round_index (optimistic uploads, older lists) default to the current
    /// round so they stay visible rather than vanishing. We match `>=`
    /// currentRound (not just `==`) so a file whose derived round_index runs
    /// ahead of the highest subtask round — e.g. a kickoff screenshot tagged to
    /// the just-opened round — is shown rather than silently dropped into the
    /// gap between the two buckets.
    private var currentRoundAttachments: [MWProjectFile] {
        attachments.filter { ($0.roundIndex ?? currentRound) >= currentRound }
    }
    /// Background attachments — files uploaded in earlier rounds, tucked behind
    /// a disclosure so a sent-back ticket doesn't show stale round-1 files up top.
    private var earlierRoundAttachments: [MWProjectFile] {
        attachments.filter { ($0.roundIndex ?? currentRound) < currentRound }
    }

    /// All checklist items for this task, across every round (ordered).
    private var allSubtasks: [MWSubtask] {
        viewModel.taskSubtasks[task.id] ?? []
    }
    /// The task's current round = highest round_index among its subtasks
    /// (defaults to 1). Derived from the subtasks themselves so it's available
    /// the moment they load, without waiting on the history fetch.
    private var currentRound: Int {
        allSubtasks.map { $0.roundIndex ?? 1 }.max() ?? 1
    }
    /// The LIVE checklist: only the current round's items. Items from earlier
    /// rounds (necessarily completed — uncompleted ones roll forward) are
    /// archived out of the checklist and live in the rounds history feed.
    private var subtasks: [MWSubtask] {
        allSubtasks.filter { ($0.roundIndex ?? 1) == currentRound }
    }
    private var subtaskDoneCount: Int { subtasks.filter { $0.isDone }.count }

    /// Free-form notes/comments — the `activity` rows from the task history.
    private var notes: [MWTaskHistoryEntry] {
        history.filter { $0.eventType == "activity" }
    }

    /// The ticket's update log — the same event set the card badge counts
    /// (`TicketUpdatesStore.countedEventTypes`), newest first. Read-only audit
    /// trail; not a checklist.
    private var updateEvents: [MWTaskHistoryEntry] {
        history
            .filter { TicketUpdatesStore.countedEventTypes.contains($0.eventType) }
            .sorted { $0.createdAt > $1.createdAt }
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

    /// Inline assignee control on the viewer: assign to me, any collaborator, or
    /// unassign — no need to open the editor. Writes via the existing task PATCH.
    private var assigneeMenu: some View {
        Menu {
            if let uid = appState.currentUser?.id, uid != task.assignedTo {
                Button { assign(uid) } label: { Label("Assign to me", systemImage: "person.fill") }
            }
            ForEach(viewModel.collaborators) { c in
                Button { assign(c.userId) } label: {
                    if c.userId == task.assignedTo {
                        Label(c.name, systemImage: "checkmark")
                    } else {
                        Text(c.name)
                    }
                }
            }
            if task.assignedTo != nil {
                Divider()
                Button("Unassign") { assign(nil) }
            }
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "person.crop.circle").font(.system(size: 8))
                Text(assigneeName ?? "Assign").font(.system(size: 9, weight: .semibold))
                Image(systemName: "chevron.down").font(.system(size: 6, weight: .bold))
            }
            .foregroundColor(.secondary)
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(Color.zinc800).cornerRadius(3)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Assign this task")
    }

    private func assign(_ userId: String?) {
        // nil → "" clears server-side; a UUID assigns. Other patch fields stay
        // nil so encodeIfPresent leaves them untouched.
        let patch = MatchaWorkService.ProjectTaskPatch(assignedTo: userId ?? "")
        Task { await viewModel.updateTask(id: task.id, patch: patch) }
    }

    private var columnLabel: String {
        task.boardColumn
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }

    var body: some View {
        ScrollView {
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
                .help("Copy ticket as text + screenshot paths (for Claude Code)")
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
                assigneeMenu
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
               task.boardColumn == "changes_requested" || task.boardColumn == "in_progress"
                || task.boardColumn == "todo" {
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

            // The latest round, surfaced up top so the current changes-requested
            // + what got fixed is obvious without expanding History (the review
            // note is cleared server-side on re-submit; History is the durable
            // record). Hidden on single-round tickets.
            currentRoundCard

            // Unviewed updates — what changed on this ticket since the user last
            // checked it off. Separate from the checklist (which is work-done).
            updatesSection

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

            // Discussion: the always-on in-ticket Q&A thread (composer + notes).
            // Available in every column — clarifying questions shouldn't sit
            // behind a toggle.
            discussionSection

            if !attachments.isEmpty {
                attachmentsSection
            }

            // History: rounds + audit trail — the background (prior rounds, who
            // moved what, what got fixed). Collapsed by default so the active
            // work (checklist + feedback + discussion) leads.
            if showHistory {
                historySection
            } else {
                historyToggle
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
        }
        .frame(width: 600)
        .frame(maxHeight: 760)
        .background(Color.appBackground)
        .task {
            // Ensure the per-user updates store is bound to this ticket's
            // project (idempotent if the board already configured it; corrects
            // it if the viewer was opened from a non-board surface).
            TicketUpdatesStore.shared.configure(
                userId: appState.currentUser?.id, projectId: viewModel.project?.id)
            if viewModel.taskFiles[task.id] == nil {
                await viewModel.loadTaskFiles(taskId: task.id)
            }
            await viewModel.loadSubtasks(taskId: task.id)
            // Discussion is always shown, so load history once on open to
            // populate the notes thread (and the collapsed rounds feed).
            if !historyLoaded { await loadHistory() }
        }
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
        .sheet(isPresented: $showingNewRoundSheet) {
            NewRoundSheet(
                nextRoundIndex: rounds.count + 1,
                openSubtasks: subtasks.filter { !$0.isDone },
                onCancel: { showingNewRoundSheet = false },
                onSubmit: { suggestedFix, body, pending, completedIds in
                    await submitNewRound(
                        suggestedFix: suggestedFix,
                        body: body,
                        pending: pending,
                        completedSubtaskIds: completedIds
                    )
                }
            )
        }
    }

    /// Sheet-callback path for starting a new round. Mirrors `submitNote`:
    /// uploads pending attachments first (so file ids exist before being
    /// referenced in the kick-off note), then calls the rounds endpoint.
    /// Returns true on success so the sheet can dismiss + clear state.
    @MainActor
    private func submitNewRound(
        suggestedFix: String,
        body: String,
        pending: [PendingAttachment],
        completedSubtaskIds: [String]
    ) async -> Bool {
        guard let pid = viewModel.project?.id else { return false }
        // Persist the completions the user just acknowledged BEFORE opening the
        // round, so the backend archives those items on the current round and
        // only rolls the still-unfinished ones forward into the new round.
        for sid in completedSubtaskIds {
            await viewModel.toggleSubtask(taskId: task.id, subtaskId: sid, isDone: true)
        }
        var uploadedIds: [String] = []
        for att in pending {
            guard let id = await viewModel.uploadTaskFile(
                taskId: task.id,
                data: att.data,
                filename: att.filename,
                mimeType: att.mimeType
            ) else {
                return false
            }
            uploadedIds.append(id)
        }
        do {
            try await MatchaWorkService.shared.startNewRound(
                projectId: pid,
                taskId: task.id,
                suggestedFixTitle: suggestedFix,
                body: body.isEmpty ? nil : body,
                attachmentIds: uploadedIds.isEmpty ? nil : uploadedIds
            )
            // Reload BOTH history (for round_started + activity rows) and the
            // subtask list (for the headline subtask just created) so the
            // checklist + rounds feed both reflect the new state.
            await loadHistory()
            await viewModel.loadSubtasks(taskId: task.id)
            showingNewRoundSheet = false
            return true
        } catch {
            return false
        }
    }

    private func loadHistory() async {
        guard let pid = viewModel.project?.id else { return }
        loadingHistory = true
        defer { loadingHistory = false }
        if let rows = try? await MatchaWorkService.shared.fetchTaskHistory(
            projectId: pid, taskId: task.id
        ) {
            history = rows
        }
        historyLoaded = true
    }

    /// Collapsed stand-in for the rounds + audit History feed (the background).
    /// History is already loaded on open for the Discussion thread, so tapping
    /// just reveals it; the lazy fetch stays as a safety net.
    private var historyToggle: some View {
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

    // MARK: - "You are here" state banner

    private struct StatePhase {
        let label: String
        let owner: String
        let color: Color
        let icon: String
    }

    private var currentPhase: StatePhase {
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
            // Round number comes from the subtasks (currentRound), not the
            // history feed — so it shows the moment the ticket opens, without
            // forcing the now-lazy history fetch.
            if currentRound > 0 {
                Text("Round \(currentRound)")
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

    // MARK: - History (rounds-grouped audit) + Discussion (notes thread)

    /// Structural history grouped into review-cycle rounds for the History feed.
    /// A new round opens on each `round_started` event (logged when a reviewer
    /// sends a card back, or someone starts a manual round). Activity notes are
    /// stripped here — they live in the separate Discussion thread, so the
    /// rounds feed is purely the structural audit trail (moves, subtask flips,
    /// the send-back event).
    private var rounds: [TaskRound] {
        TaskRound.build(from: history.filter { $0.eventType != "activity" })
    }

    /// The latest round rendered inline in the foreground — surfaces the current
    /// changes-requested + "fixed in round N-1" so the user doesn't have to
    /// expand History to see what changed. Multi-round tickets only.
    @ViewBuilder
    private var currentRoundCard: some View {
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

    /// The in-ticket Q&A thread: a note composer plus the activity notes,
    /// newest-first. Always visible in every column so clarifying questions
    /// are one click away. Posting a note bells the other participants.
    @ViewBuilder
    private var discussionSection: some View {
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
            }

            noteComposer

            // Activity notes only, newest-first so the latest sits right under
            // the composer. Structural events (moves, subtask flips, round
            // starts) are intentionally NOT here — they live in History.
            if !notes.isEmpty {
                ForEach(Array(notes.reversed())) { note in
                    NoteRow(
                        entry: note,
                        files: attachments,
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
    private var historySection: some View {
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

    /// UPDATES — a read-only audit log of what changed on this ticket (comments
    /// / round changes / subtasks added / moves+send-backs), newest first. Like
    /// a commit history: it's there to reconcile discrepancies, not to tick off.
    /// Collapsed by default (never auto-opens with the ticket). Expanding it
    /// acknowledges the log → clears the card's unviewed-updates badge.
    @ViewBuilder
    private var updatesSection: some View {
        let events = updateEvents
        if !events.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Button {
                    let opening = !showUpdates
                    withAnimation { showUpdates.toggle() }
                    if opening {
                        TicketUpdatesStore.shared.markAllViewed(
                            taskId: task.id, eventIds: events.map(\.id))
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "clock.arrow.2.circlepath")
                            .font(.system(size: 10))
                            .foregroundColor(.blue)
                        Text("UPDATES")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                            .tracking(0.5)
                        Text("\(events.count)")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                        Spacer()
                        Image(systemName: showUpdates ? "chevron.up" : "chevron.down")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if showUpdates {
                    ForEach(events) { e in UpdateLogRow(entry: e) }
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.zinc800.opacity(0.35))
            .cornerRadius(6)
        }
    }

    @ViewBuilder
    private var noteComposer: some View {
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
    private func replyingToBanner(_ note: MWTaskHistoryEntry) -> some View {
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
                attachmentIds: uploadedIds.isEmpty ? nil : uploadedIds,
                replyTo: replyingToNote?.id
            )
            newNote = ""
            pendingAttachments = []
            replyingToNote = nil
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

    /// Copies the ticket as a single TEXT blob tuned for Claude Code: title,
    /// status, description, checklist (subtasks), and the screenshots written
    /// out as LOCAL file paths Claude Code can open with its Read tool.
    ///
    /// Deliberately text-only — no image bytes on the clipboard. Claude Code
    /// (and most CLIs) grab image data whenever it's present and drop the text,
    /// which loses the ticket context. Local paths sidestep that: one paste
    /// carries the full ticket AND loadable screenshots. (These are real local
    /// files, unlike the dead CloudFront URLs the export used to emit.)
    @MainActor
    private func copyTicketToClipboard() async {
        isCopying = true

        // Download up to 6 image attachments and write them to a per-task temp
        // dir so their paths are real + readable. Only successfully-written
        // files contribute a path (never list an unreadable one).
        let images = Array(attachments.filter { $0.isImage }.prefix(6))
        let tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("werk-ticket-\(task.id)", isDirectory: true)
        try? FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)

        var screenshotPaths: [String] = []
        for (idx, img) in images.enumerated() {
            guard let url = URL(string: img.storageUrl),
                  let (data, _) = try? await URLSession.shared.data(from: url) else { continue }
            let safeName = img.filename.isEmpty ? "image-\(idx).png" : img.filename
            let fileURL = tmpDir.appendingPathComponent("\(idx)-\(safeName)")
            if (try? data.write(to: fileURL)) != nil {
                screenshotPaths.append(fileURL.path)
            }
        }

        let markdown = TaskClipboardExporter.markdown(
            for: task,
            assigneeName: assigneeName,
            columnLabel: columnLabel,
            attachments: attachments,
            subtasks: subtasks,
            screenshotPaths: screenshotPaths,
        )

        let board = NSPasteboard.general
        board.clearContents()
        board.setString(markdown, forType: .string)

        isCopying = false
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

/// One round on a kanban ticket — a modular sub-todo housed inside the
/// parent ticket. Rounds chain together explicitly: any collaborator
/// hits "Start Next Round," names the suggested fix, and a new round
/// opens. Round 1 covers the initial work from creation up to the first
/// `round_started` event; each subsequent `round_started` row in
/// mw_task_history opens a new round and lands at the TOP of it.
///
/// Events inside a round stay chronological so the round reads as a
/// self-contained story: "round opened (suggested fix: X) · subtask
/// added · note · ... · next round_started → this round closes."
struct TaskRound: Identifiable {
    let index: Int
    let events: [MWTaskHistoryEntry]
    let isLatest: Bool

    var id: Int { index }

    /// Round title — for round N>=2, the `suggested_fix_title` from the
    /// opening `round_started` event. For round 1, falls back to a
    /// generic label so the UI always has something to render.
    var title: String {
        if let opener = events.first, opener.eventType == "round_started",
           let t = (opener.metadata?["title"])?.trimmingCharacters(in: .whitespacesAndNewlines),
           !t.isEmpty {
            return t
        }
        return "Initial work"
    }

    /// True when this round was opened by an explicit `round_started`
    /// event (vs the implicit round 1 that starts at task creation).
    var hasExplicitOpener: Bool {
        events.first?.eventType == "round_started"
    }

    /// Subtask titles completed during this round. Drives the "Fixed in
    /// Round N-1" inheritance block at the top of the NEXT round so the
    /// reviewer sees what got addressed at a glance.
    var fixedSubtaskTitles: [String] {
        events
            .filter { $0.eventType == "subtask_completed" }
            .compactMap { ($0.metadata?["title"])?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    /// Highest-signal column the round currently sits in, used in the round
    /// header chip ("Round 3 · In Review", "Round 2 · Sent back"). Derived
    /// from the last column_change in this round; defaults to "Active" /
    /// "Closed" based on whether this is the latest round.
    func phaseLabel(isLatest: Bool) -> String {
        if let last = events.reversed().first(where: { $0.eventType == "column_change" }),
           let col = last.toValue {
            switch col {
            case "todo": return "Todo"
            case "in_progress": return "In Progress"
            case "review": return "In Review"
            case "changes_requested": return "Sent Back"
            case "done": return "Done"
            default: return col.replacingOccurrences(of: "_", with: " ").capitalized
            }
        }
        return isLatest ? "Active" : "Closed"
    }

    func phaseColor(isLatest: Bool) -> Color {
        if let last = events.reversed().first(where: { $0.eventType == "column_change" }) {
            switch last.toValue ?? "" {
            case "review": return .blue
            case "changes_requested": return .orange
            case "done": return .matcha500
            case "in_progress": return .yellow
            default: break
            }
        }
        return isLatest ? .matcha500 : .secondary
    }

    /// Build rounds from a flat history list. Round boundaries are EXPLICIT
    /// — only `round_started` events open new rounds. Column moves are
    /// informational events that live inside whatever round they fall in,
    /// no longer triggering boundaries on their own.
    static func build(from history: [MWTaskHistoryEntry]) -> [TaskRound] {
        let sorted = history.sorted { $0.createdAt < $1.createdAt }
        var buckets: [[MWTaskHistoryEntry]] = [[]]
        for e in sorted {
            if e.eventType == "round_started" {
                // Open a new round; the round_started event itself goes at
                // the top of the new round so the title + subtask hook
                // render first.
                buckets.append([])
            }
            buckets[buckets.count - 1].append(e)
        }
        if buckets.last?.isEmpty == true { buckets.removeLast() }
        if buckets.isEmpty { return [] }
        return buckets.enumerated().map { idx, events in
            TaskRound(index: idx + 1, events: events, isLatest: idx == buckets.count - 1)
        }
    }
}

/// Renders one TaskRound as a self-contained sub-ticket card: header
/// (Round N · CURRENT · phase) + title (suggested fix) + optional
/// "Fixed in previous round" inheritance summary + this round's events.
/// Latest round is expanded and gets a phase-colored border; older
/// rounds collapse under DisclosureGroup so a thrashing ticket doesn't
/// bury the active sub-todo under audit-log noise.
private struct RoundView: View {
    let round: TaskRound
    let previousFixed: [String]
    let files: [MWProjectFile]
    let onPreview: (MWProjectFile) -> Void

    @State private var isExpanded: Bool

    init(
        round: TaskRound,
        previousFixed: [String],
        files: [MWProjectFile],
        onPreview: @escaping (MWProjectFile) -> Void
    ) {
        self.round = round
        self.previousFixed = previousFixed
        self.files = files
        self.onPreview = onPreview
        self._isExpanded = State(initialValue: round.isLatest)
    }

    private var phaseLabel: String { round.phaseLabel(isLatest: round.isLatest) }
    private var phaseColor: Color { round.phaseColor(isLatest: round.isLatest) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            DisclosureGroup(isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 8) {
                    // "Fixed in Round N-1" inheritance block. Only shown on
                    // rounds 2+, only when the prior round actually
                    // completed something. Gives the reader at-a-glance
                    // continuity: "this round picks up from these closed
                    // items."
                    if !previousFixed.isEmpty {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("FIXED IN ROUND \(round.index - 1)")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(.matcha500)
                                .tracking(0.6)
                            ForEach(Array(previousFixed.enumerated()), id: \.offset) { _, title in
                                HStack(spacing: 6) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(.matcha500)
                                    Text(title)
                                        .font(.system(size: 11))
                                        .foregroundColor(.white.opacity(0.85))
                                        .strikethrough()
                                        .lineLimit(2)
                                }
                            }
                        }
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.matcha500.opacity(0.08))
                        .cornerRadius(5)
                    }

                    // A busy round (many moves/notes/subtask events) makes the
                    // card runaway-tall. Cap it and scroll internally past a
                    // threshold; short rounds render inline with no scrollbar.
                    let eventsStack = VStack(alignment: .leading, spacing: 4) {
                        ForEach(round.events) { event in
                            EventRow(event: event, files: files, onPreview: onPreview)
                        }
                    }
                    if round.events.count > 8 {
                        ScrollView { eventsStack }
                            .frame(height: 340)
                    } else {
                        eventsStack
                    }
                }
                .padding(.top, 6)
                .padding(.leading, 4)
            } label: {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        if round.isLatest {
                            HStack(spacing: 3) {
                                Circle()
                                    .fill(phaseColor)
                                    .frame(width: 6, height: 6)
                                Text("CURRENT")
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundColor(phaseColor)
                                    .tracking(0.7)
                            }
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(phaseColor.opacity(0.18))
                            .cornerRadius(3)
                        }
                        Text("Round \(round.index)")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.white.opacity(0.9))
                        Text("·")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text(phaseLabel)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(phaseColor)
                            .tracking(0.5)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(phaseColor.opacity(0.15))
                            .cornerRadius(3)
                        Spacer()
                        Text("\(round.events.count) event\(round.events.count == 1 ? "" : "s")")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                    }
                    // Round title (the suggested fix) — prominent because
                    // each round is a modular sub-todo with its own scope.
                    Text(round.title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
            }
            .accentColor(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(round.isLatest ? Color.zinc800.opacity(0.55) : Color.zinc800.opacity(0.3))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(round.isLatest ? phaseColor.opacity(0.45) : Color.clear, lineWidth: 1.5)
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

    /// Only "ownership-meaningful" events show an avatar: notes (via NoteRow),
    /// subtask additions, ticket creation, and round openings. Status moves,
    /// reassignments, edits, and subtask state-flips revert to the original
    /// SF-Symbol-only row — the actor name in the secondary line is enough
    /// for those low-signal audit events.
    private static let avatarBearingEvents: Set<String> = [
        "created", "round_started", "subtask_added",
    ]

    var body: some View {
        if event.eventType == "activity" {
            // Notes get the full card treatment (body + actor + thumbs).
            NoteRow(entry: event, files: files, onPreview: onPreview)
        } else {
            HStack(alignment: .top, spacing: 8) {
                if Self.avatarBearingEvents.contains(event.eventType),
                   let actorId = event.actorUserId {
                    ChannelAvatarView(
                        senderId: actorId,
                        payloadURL: event.actorAvatarUrl,
                        name: event.actorName ?? "",
                        size: 22
                    )
                } else {
                    Image(systemName: Self.icon(for: event.eventType))
                        .font(.system(size: 11))
                        .foregroundColor(Self.tint(for: event.eventType))
                        .frame(width: 22, alignment: .center)
                }
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

    fileprivate static func icon(for event: String) -> String {
        switch event {
        case "created": return "plus.circle.fill"
        case "column_change": return "arrow.right.circle"
        case "assignee_change": return "person.circle"
        case "description_change": return "text.alignleft"
        case "progress_note_change": return "note.text"
        case "review_rejected": return "arrow.uturn.backward.circle"
        case "round_started": return "flag.circle.fill"
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
        case "round_started": return .matcha500
        case "subtask_added": return .blue
        case "subtask_completed": return .matcha500
        case "subtask_uncompleted": return .orange
        case "subtask_deleted": return .red
        case "deleted": return .red
        default: return .secondary
        }
    }

    fileprivate static func describe(_ e: MWTaskHistoryEntry) -> String {
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
        case "round_started":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) opened a new round"
                : "\(who) opened a new round: \u{201C}\(title)\u{201D}"
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

/// One row in the read-only UPDATES audit log: an event icon, a compact label,
/// and the timestamp. No interaction — it's a reference trail, not a checklist.
private struct UpdateLogRow: View {
    let entry: MWTaskHistoryEntry

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: Self.icon(entry))
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .frame(width: 16, alignment: .center)
            VStack(alignment: .leading, spacing: 1) {
                Text(Self.label(entry))
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.85))
                    .fixedSize(horizontal: false, vertical: true)
                Text(PacificDateFormatter.absolute(entry.createdAt) ?? entry.createdAt)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 2)
    }

    private static func icon(_ e: MWTaskHistoryEntry) -> String {
        e.eventType == "activity" ? "bubble.left" : EventRow.icon(for: e.eventType)
    }

    /// Compact one-liner. Reuses EventRow.describe for structural events;
    /// activity (comments) get bespoke wording incl. an image-only fallback.
    private static func label(_ e: MWTaskHistoryEntry) -> String {
        guard e.eventType == "activity" else { return EventRow.describe(e) }
        let who = e.actorName?.isEmpty == false ? e.actorName! : "Someone"
        let body = (e.metadata?["body"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\n", with: " ")
        if !body.isEmpty {
            let excerpt = body.count > 80 ? String(body.prefix(80)) + "\u{2026}" : body
            return "\(who) commented: \u{201C}\(excerpt)\u{201D}"
        }
        if let ids = e.attachmentIds, !ids.isEmpty {
            return ids.count == 1 ? "\(who) added an image" : "\(who) added \(ids.count) images"
        }
        return "\(who) commented"
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
    var onReply: (() -> Void)? = nil
    @State private var isHovered = false

    private var body_: String {
        (entry.metadata?["body"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var linkedFiles: [MWProjectFile] {
        guard let ids = entry.attachmentIds, !ids.isEmpty else { return [] }
        let idSet = Set(ids)
        return files.filter { idSet.contains($0.id) }
    }

    /// Set on notes that reply to an earlier comment — resolved server-side and
    /// stashed in metadata so we can render the quoted parent inline.
    private var replyParentName: String? { entry.metadata?["reply_to_name"] }
    private var replyParentExcerpt: String? {
        let e = (entry.metadata?["reply_to_excerpt"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return e.isEmpty ? nil : e
    }

    var body: some View {
        let bodyText = body_
        let linked = linkedFiles
        if bodyText.isEmpty && linked.isEmpty { EmptyView() } else {
            HStack(alignment: .top, spacing: 8) {
                // Per-note avatar on the LEFT so a row of stacked notes
                // reads like a chat thread — eye drops down the avatar
                // column to identify who wrote what without parsing the
                // actor name in the footer.
                if let actorId = entry.actorUserId {
                    ChannelAvatarView(
                        senderId: actorId,
                        payloadURL: entry.actorAvatarUrl,
                        name: entry.actorName ?? "",
                        size: 24
                    )
                } else {
                    // System-generated notes are rare; keep a neutral
                    // grey circle so the row still aligns.
                    Circle()
                        .fill(Color.zinc800)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Image(systemName: "text.bubble")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        )
                }
                VStack(alignment: .leading, spacing: 4) {
                    // Quoted parent — shows what this note is replying to.
                    if let excerpt = replyParentExcerpt {
                        HStack(spacing: 5) {
                            Rectangle()
                                .fill(Color.matcha500.opacity(0.7))
                                .frame(width: 2)
                                .cornerRadius(1)
                            VStack(alignment: .leading, spacing: 0) {
                                if let name = replyParentName {
                                    Text(name)
                                        .font(.system(size: 8, weight: .semibold))
                                        .foregroundColor(.matcha500)
                                }
                                Text(excerpt)
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                                    .lineLimit(2)
                            }
                        }
                        .padding(.leading, 1)
                    }
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
                    HStack(spacing: 8) {
                        Text("\((entry.actorName?.isEmpty == false ? entry.actorName! : "Someone")) · \(PacificDateFormatter.absolute(entry.createdAt) ?? "")")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                        if let onReply, isHovered {
                            Button(action: onReply) {
                                HStack(spacing: 2) {
                                    Image(systemName: "arrowshape.turn.up.left")
                                        .font(.system(size: 8))
                                    Text("Reply")
                                        .font(.system(size: 9, weight: .semibold))
                                }
                                .foregroundColor(.matcha500)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.zinc800.opacity(0.5))
            .cornerRadius(5)
            .onHover { isHovered = $0 }
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
    let collaborators: [MWProjectCollaborator]
    let currentUserId: String?
    let onToggle: () -> Void
    let onDelete: () -> Void
    let onAssign: (String?) -> Void
    @State private var isHovered = false
    @State private var showingAssign = false

    private var assignee: MWProjectCollaborator? {
        guard let id = item.assignedTo else { return nil }
        return collaborators.first { $0.userId == id }
    }

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
                .textSelection(.enabled)
                .contextMenu {
                    Button("Copy") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(item.title, forType: .string)
                    }
                }
            Spacer(minLength: 0)
            assigneeMenu
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

    // A plain Button (NOT a Menu label) — macOS Menu labels rasterize a
    // resizable image oddly (clipShape ignored → square/garbled avatar). A
    // Button renders ChannelAvatarView as the same clean 18×18 circle it shows
    // in the discussion feed. The picker is a confirmationDialog.
    private var assigneeMenu: some View {
        Button { showingAssign = true } label: {
            if let id = item.assignedTo {
                ChannelAvatarView(
                    senderId: id,
                    payloadURL: assignee?.avatarUrl,
                    name: assignee?.name ?? "",
                    size: 18
                )
            } else {
                Circle()
                    .strokeBorder(Color.secondary.opacity(isHovered ? 0.7 : 0.35),
                                  style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    .frame(width: 18, height: 18)
                    .overlay(
                        Image(systemName: "plus")
                            .symbolRenderingMode(.monochrome)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary.opacity(isHovered ? 0.9 : 0.45))
                    )
            }
        }
        .buttonStyle(.plain)
        .help(assignee?.name ?? "Assign")
        .confirmationDialog("Assign checklist item", isPresented: $showingAssign, titleVisibility: .visible) {
            if let uid = currentUserId, uid != item.assignedTo {
                Button("Assign to me") { onAssign(uid) }
            }
            ForEach(collaborators) { c in
                Button(c.userId == item.assignedTo ? "✓ \(c.name)" : c.name) { onAssign(c.userId) }
            }
            if item.assignedTo != nil {
                Button("Unassign", role: .destructive) { onAssign(nil) }
            }
            Button("Cancel", role: .cancel) {}
        }
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
            // Uploader pfp so "who attached this" is visible at a glance —
            // matches the per-event avatar pattern in the rounds feed.
            if let uploaderId = file.uploadedBy {
                ChannelAvatarView(
                    senderId: uploaderId,
                    payloadURL: file.uploaderAvatarUrl,
                    name: file.uploaderName ?? "",
                    size: 20
                )
            }
            if file.isImage, let url = URL(string: file.storageUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().interpolation(.medium).aspectRatio(contentMode: .fill)
                    case .failure:
                        Color.zinc800.overlay(
                            Image(systemName: "photo").font(.system(size: 10)).foregroundColor(.secondary))
                    default:
                        Color.zinc800.overlay(ProgressView().controlSize(.small))
                    }
                }
                .frame(width: 30, height: 30)
                .clipShape(RoundedRectangle(cornerRadius: 4))
            } else {
                Image(systemName: "doc")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .frame(width: 30, height: 30)
            }
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
/// (title, status, assignee, description, checklist) into Claude Code /
/// Codex / any chat that accepts markdown. Screenshots are referenced by
/// LOCAL file path (`screenshotPaths`) so Claude Code can open them with its
/// Read tool — not by CloudFront URL, which CLIs can't fetch.
enum TaskClipboardExporter {
    static func markdown(
        for task: MWProjectTask,
        assigneeName: String?,
        columnLabel: String,
        attachments: [MWProjectFile],
        subtasks: [MWSubtask] = [],
        screenshotPaths: [String] = [],
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

/// Sheet for opening a new round on a ticket. Any collaborator can hit
/// "Start Next Round" → name the suggested fix → optionally add a
/// kick-off note + paste a screenshot → submit. The fix becomes the
/// new round's headline subtask AND the round's display title.
private struct NewRoundSheet: View {
    let nextRoundIndex: Int
    /// The current round's still-open checklist items. The person starting a
    /// round must say which (if any) they actually finished before it rolls
    /// the rest forward.
    let openSubtasks: [MWSubtask]
    let onCancel: () -> Void
    /// Returns true if submit succeeded and the sheet should dismiss.
    let onSubmit: (_ suggestedFix: String, _ body: String, _ pending: [PendingAttachment], _ completedSubtaskIds: [String]) async -> Bool

    @State private var suggestedFix = ""
    @State private var noteBody = ""
    @State private var pending: [PendingAttachment] = []
    @State private var completedIds: Set<String> = []
    @State private var submitting = false
    @State private var error: String?

    private var canSubmit: Bool {
        !suggestedFix.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("START ROUND \(nextRoundIndex)")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.matcha500)
                        .tracking(0.5)
                    Text("Chain a new sub-todo onto this ticket")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.85))
                }
                Spacer()
                Button(action: onCancel) {
                    Image(systemName: "xmark")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            // Force the round-opener to account for the current checklist: tick
            // what's actually done (archives onto this round) — the rest rolls
            // forward. Only shown when there are open items to resolve.
            if !openSubtasks.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("DID YOU COMPLETE ANY OF THESE?")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.matcha500)
                        .tracking(0.5)
                    Text("Check off what's done — it archives into this round; unchecked items carry into Round \(nextRoundIndex).")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    ForEach(openSubtasks) { item in
                        Button {
                            if completedIds.contains(item.id) { completedIds.remove(item.id) }
                            else { completedIds.insert(item.id) }
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: completedIds.contains(item.id) ? "checkmark.circle.fill" : "circle")
                                    .font(.system(size: 13))
                                    .foregroundColor(completedIds.contains(item.id) ? .matcha500 : .secondary)
                                Text(item.title)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.9))
                                    .strikethrough(completedIds.contains(item.id))
                                    .lineLimit(2)
                                Spacer(minLength: 0)
                            }
                            .padding(.vertical, 3)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.matcha500.opacity(0.08))
                .cornerRadius(6)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("SUGGESTED FIX")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                TextField("e.g. Add EIN validation before export", text: $suggestedFix)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white)
                    .padding(8)
                    .background(Color.zinc800.opacity(0.7))
                    .cornerRadius(5)
                    .onSubmit {
                        if canSubmit { Task { await submit() } }
                    }
                Text("Becomes a new checklist item AND this round's title.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("KICK-OFF NOTE (optional)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                TextEditor(text: $noteBody)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.9))
                    .scrollContentBackground(.hidden)
                    .padding(5)
                    .frame(height: 80)
                    .background(Color.zinc800.opacity(0.6))
                    .cornerRadius(5)
                HStack(spacing: 8) {
                    Button {
                        attachFileFromDisk()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "paperclip").font(.system(size: 11))
                            Text("Attach file").font(.system(size: 11))
                        }
                        .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    Button {
                        attachImageFromClipboard()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "doc.on.clipboard").font(.system(size: 11))
                            Text("Paste screenshot").font(.system(size: 11))
                        }
                        .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    Spacer()
                }
                if !pending.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(pending) { att in
                                PendingAttachmentChip(attachment: att) {
                                    pending.removeAll { $0.id == att.id }
                                }
                            }
                        }
                    }
                }
            }

            if let err = error {
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
            }

            HStack {
                Spacer()
                Button("Cancel", action: onCancel)
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Button {
                    Task { await submit() }
                } label: {
                    if submitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Open Round \(nextRoundIndex)")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(canSubmit ? .matcha500 : .secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSubmit || submitting)
            }
        }
        .padding(18)
        .frame(width: 480)
        .background(Color.appBackground)
    }

    private func submit() async {
        let title = suggestedFix.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, !submitting else { return }
        submitting = true
        error = nil
        let ok = await onSubmit(title, noteBody, pending, Array(completedIds))
        if !ok {
            error = "Couldn't open the round. Try again."
        }
        submitting = false
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
                let ext = (filename as NSString).pathExtension.lowercased()
                let mime = (UTType(filenameExtension: ext)?.preferredMIMEType) ?? "application/octet-stream"
                pending.append(PendingAttachment(data: data, filename: filename, mimeType: mime))
            }
        }
    }

    private func attachImageFromClipboard() {
        let pb = NSPasteboard.general
        if let png = pb.data(forType: .png) {
            pending.append(PendingAttachment(data: png, filename: clipboardScreenshotName(ext: "png"), mimeType: "image/png"))
            return
        }
        if let tiff = pb.data(forType: .tiff),
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            pending.append(PendingAttachment(data: png, filename: clipboardScreenshotName(ext: "png"), mimeType: "image/png"))
            return
        }
        let jpegType = NSPasteboard.PasteboardType(UTType.jpeg.identifier)
        if let jpeg = pb.data(forType: jpegType) {
            pending.append(PendingAttachment(data: jpeg, filename: clipboardScreenshotName(ext: "jpg"), mimeType: "image/jpeg"))
        }
    }

    private func clipboardScreenshotName(ext: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd-HHmmss"
        return "screenshot-\(f.string(from: Date())).\(ext)"
    }
}
