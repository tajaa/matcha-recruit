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
///
/// This view is split across files to keep each focused:
/// - `TaskViewerSheet.swift` (this file) — stored state, derived data, `body`.
/// - `TaskViewer/TaskViewerSheet+Graph.swift` — the activity-graph mode.
/// - `TaskViewer/TaskViewerSheet+Sections.swift` — the list-mode section views.
/// - `TaskViewer/TaskViewerSheet+Actions.swift` — history load + submit actions.
/// The row/card subviews + models live in the `TaskViewer/` folder alongside.
/// Members are `internal` (not `private`) because the extensions live in
/// separate files; nothing outside this view references them.
struct TaskViewerSheet: View {
    let task: MWProjectTask
    @Bindable var viewModel: ProjectDetailViewModel
    let onEdit: () -> Void
    let onClose: () -> Void
    @Environment(AppState.self) var appState

    @State var previewFile: MWProjectFile?
    @State var history: [MWTaskHistoryEntry] = []
    /// Discussion (the in-ticket Q&A thread) is always visible and renders the
    /// activity notes, so history is fetched once on open. `historyLoaded`
    /// guards that one-time fetch; the rounds/audit feed stays collapsed behind
    /// `showHistory` so the audit trail is opt-in, not in the way.
    @State var showHistory = false
    @State var historyLoaded = false
    @State var loadingHistory = false
    /// Earlier-round attachments tuck behind a disclosure so the foreground
    /// ATTACHMENTS list shows only the current round's files.
    @State var showEarlierAttachments = false
    @State var didCopy = false
    @State var isCopying = false
    @State var newNote = ""
    @State var addingNote = false
    @FocusState var isNoteFieldFocused: Bool
    /// The discussion comment the composer is currently replying to, if any.
    /// Drives the "Replying to …" banner and threads `reply_to` through submit.
    @State var replyingToNote: MWTaskHistoryEntry?
    @State var isRejecting = false
    @State var rejectNote = ""
    @State var submitting = false
    @State var newSubtask = ""
    @State var addingSubtask = false
    /// Pending image attachments queued for the next note submit. Cleared
    /// after a successful submit. Each entry is held in-memory until upload.
    @State var pendingAttachments: [PendingAttachment] = []
    /// Open-state for the "Start Next Round" sheet. Sheet is hosted at the
    /// root of TaskViewerSheet so it lives above all section content.
    @State var showingNewRoundSheet = false
    /// List (the default sections) vs the collaboration activity graph — a
    /// git-network-style view where each key action is a node in its actor's
    /// lane and edges cross lanes to show handoffs between collaborators.
    @State var viewMode: ViewerMode = .list

    var attachments: [MWProjectFile] {
        viewModel.taskFiles[task.id] ?? []
    }

    /// Foreground attachments — the current round's files. Files with no
    /// round_index (optimistic uploads, older lists) default to the current
    /// round so they stay visible rather than vanishing. We match `>=`
    /// currentRound (not just `==`) so a file whose derived round_index runs
    /// ahead of the highest subtask round — e.g. a kickoff screenshot tagged to
    /// the just-opened round — is shown rather than silently dropped into the
    /// gap between the two buckets.
    var currentRoundAttachments: [MWProjectFile] {
        attachments.filter { ($0.roundIndex ?? currentRound) >= currentRound }
    }
    /// Background attachments — files uploaded in earlier rounds, tucked behind
    /// a disclosure so a sent-back ticket doesn't show stale round-1 files up top.
    var earlierRoundAttachments: [MWProjectFile] {
        attachments.filter { ($0.roundIndex ?? currentRound) < currentRound }
    }

    /// All checklist items for this task, across every round (ordered).
    var allSubtasks: [MWSubtask] {
        viewModel.taskSubtasks[task.id] ?? []
    }
    /// The task's current round = highest round_index among its subtasks
    /// (defaults to 1). Derived from the subtasks themselves so it's available
    /// the moment they load, without waiting on the history fetch.
    var currentRound: Int {
        allSubtasks.map { $0.roundIndex ?? 1 }.max() ?? 1
    }
    /// The LIVE checklist: only the current round's items. Items from earlier
    /// rounds (necessarily completed — uncompleted ones roll forward) are
    /// archived out of the checklist and live in the rounds history feed.
    var subtasks: [MWSubtask] {
        allSubtasks.filter { ($0.roundIndex ?? 1) == currentRound }
    }
    var subtaskDoneCount: Int { subtasks.filter { $0.isDone }.count }

    /// Free-form notes/comments — the `activity` rows from the task history.
    var notes: [MWTaskHistoryEntry] {
        history.filter { $0.eventType == "activity" }
    }

    /// `round_started` timestamps, ascending. Anything created at/after the
    /// k-th boundary belongs to round k+1 — same derivation the backend uses for
    /// file round_index and `_current_round`, so a comment's round lines up with
    /// `currentRound` (from subtasks) and the attachment rounds.
    var roundBoundaryTimes: [String] {
        history.filter { $0.eventType == "round_started" }.map(\.createdAt).sorted()
    }
    func roundIndex(forCreatedAt createdAt: String) -> Int {
        1 + roundBoundaryTimes.reduce(into: 0) { acc, t in if t <= createdAt { acc += 1 } }
    }

    var assigneeName: String? {
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
    var assigneeMenu: some View {
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

    func assign(_ userId: String?) {
        // nil → "" clears server-side; a UUID assigns. Other patch fields stay
        // nil so encodeIfPresent leaves them untouched.
        let patch = MatchaWorkService.ProjectTaskPatch(assignedTo: userId ?? "")
        Task { await viewModel.updateTask(id: task.id, patch: patch) }
    }

    var columnLabel: String {
        task.boardColumn
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }

    /// Structural history grouped into review-cycle rounds for the History feed.
    /// A new round opens on each `round_started` event (logged when a reviewer
    /// sends a card back, or someone starts a manual round). Activity notes are
    /// stripped here — they live in the separate Discussion thread, so the
    /// rounds feed is purely the structural audit trail (moves, subtask flips,
    /// the send-back event).
    var rounds: [TaskRound] {
        TaskRound.build(from: history.filter { $0.eventType != "activity" })
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
                HStack(spacing: 2) {
                    modeButton(.list, icon: "list.bullet")
                    modeButton(.graph, icon: "point.3.connected.trianglepath.dotted")
                }
                .padding(2)
                .background(Color.zinc800)
                .cornerRadius(5)
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

            if viewMode == .list {
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
            } else {
                // Activity graph: the same history, drawn as a branching diagram
                // of collaboration — one lane per person, each action a node,
                // edges crossing lanes on handoffs.
                activityGraphSection
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
        .frame(width: viewMode == .graph ? 820 : 600)
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

    func metaPill(label: String, color: Color) -> some View {
        Text(label)
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(3)
    }
}
