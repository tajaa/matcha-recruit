import AppKit
import SwiftUI
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
    /// The contributor brief is readable on open; audit history stays folded.
    @State var showDescription = true
    @State var showSummary = false
    @State var historyLoaded = false
    @State var loadingHistory = false
    /// Earlier-round attachments tuck behind a disclosure so the foreground
    /// ATTACHMENTS list shows only the current round's files.
    @State var showEarlierAttachments = false
    @State var didCopy = false
    @State var isCopying = false
    @State var didDuplicate = false
    @State var isDuplicating = false
    @State var isSummarizing = false
    @State var newNote = ""
    @State var addingNote = false
    @State var isAddingAutoPRContext = false
    @State var didSubmitAutoPRContext = false
    @State var autoPRContextError: String?
    @State var autoPRContextExpectedNote: String?
    /// "Run AutoPR now": optimistic local state so the control flips the
    /// instant the request lands, before the next task-list refresh carries
    /// the server's `autopr_run_requested_at` back.
    @State var didRequestAutoPRRun = false
    @State var requestingAutoPRRun = false
    /// Which AutoPR control is in flight ("run" or "hold"), so two buttons
    /// that share the busy flag never show each other's progress verb.
    @State var autoPRPendingAction: String? = nil
    @State var autoPRRunError: String?
    /// Outreach a research run proposed. Empty on every ticket that never ran
    /// one, so the section simply does not render.
    @State var stagedActions: [MWStagedAction] = []
    /// The action currently being approved or closed — one at a time, so a
    /// double tap cannot fire two sends before the first returns.
    @State var resolvingActionId: String?
    @State var stagedActionError: String?
    /// Who the last approved send went to — the confirmation line under the
    /// section, cleared by the next action.
    @State var stagedActionSentTo: String?
    /// nil = not asked yet / unknown. Asked only when a sendable proposal is
    /// open; false swaps the Send button for Connect Gmail.
    @State var gmailConnected: Bool?
    @State var connectingGmail = false
    /// For a Research card: is this board granted `research`? nil = unknown
    /// (not asked, or the call failed) — the button stays enabled and the
    /// server / harness answer as before. false disables it with the reason.
    @State var researchGranted: Bool?
    @State var isNoteFieldFocused = false
    /// The discussion comment the composer is currently replying to, if any.
    /// Drives the "Replying to …" banner and threads `reply_to` through submit.
    @State var replyingToNote: MWTaskHistoryEntry?
    @State var isRejecting = false
    @State var rejectNote = ""
    @State var isApproving = false
    @State var approveNote = ""
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

    /// Artifact kinds publish `<kind>-report-<id8>-r<N>.md`; nil for PR cards.
    var autoPRReportPrefix: String? {
        switch liveAutoPRTask.category {
        case "research": return "research-report-"
        case "email": return "email-report-"
        default: return nil
        }
    }

    var autoPRReportTitle: String {
        liveAutoPRTask.category == "email" ? "Email review" : "Research report"
    }

    /// AutoPR research publishes a Markdown deliverable named
    /// `research-report-…`. Pull the newest one forward into a dedicated reader
    /// entry instead of making someone hunt through the generic attachment list.
    var researchReportAttachment: MWProjectFile? {
        guard let prefix = autoPRReportPrefix else { return nil }
        return
            attachments
            .filter { file in
                let name = file.filename.lowercased()
                let ext = (file.filename as NSString).pathExtension.lowercased()
                return name.hasPrefix(prefix)
                    && ["md", "markdown", "pdf"].contains(ext)
            }
            .sorted { ($0.createdAt ?? "") > ($1.createdAt ?? "") }
            .first
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

    /// Free-form notes/comments — the `activity` rows from the task history,
    /// minus AutoPR's bookkeeping rows (run requests, claims, staged outreach
    /// and its outcomes), which ride the same event type but are not
    /// discussion. A staged email draft in particular must not appear here as
    /// a bot comment: it is rendered, with its buttons, by `outreachSection`.
    var notes: [MWTaskHistoryEntry] {
        history.filter { $0.eventType == "activity" && !GraphGeom.isBookkeeping($0) }
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
                Button {
                    assign(uid)
                } label: {
                    Label("Assign to me", systemImage: "person.fill")
                }
            }
            ForEach(viewModel.collaborators) { c in
                Button {
                    assign(c.userId)
                } label: {
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
                Image(systemName: "person.crop.circle").font(.ticket(size: 12))
                Text(assigneeName ?? "Assign").font(.ticket(size: 11))
                    .lineLimit(1).truncationMode(.middle)
                Image(systemName: "chevron.down").font(.ticket(size: 6))
            }
            .foregroundColor(.secondary)

        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .frame(maxWidth: 180)
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
            VStack(alignment: .leading, spacing: 20) {
                ticketToolbar
                VStack(alignment: .leading, spacing: 12) {
                    Text(task.title)
                        .font(.ticket(size: 23))
                        .foregroundColor(appState.themeText)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                    metaLine
                }
                Divider().opacity(0.5)

                // THE directive — the single salient "do this now", chosen by phase
                // (send-back, review prompt, progress note, or the brief). Everything
                // below this is supporting detail.
                directiveHero

                if viewMode == .list {
                    // Contributor-authored context leads in list mode; graph mode
                    // uses the activity lanes as its human-authored context.
                    descriptionCollapsible
                }

                // Automation provenance and controls are ticket state, not one
                // presentation mode's content. Keep them visible in both list and
                // graph mode, along with the first-class research deliverable.
                autoSetupBanner
                autoPRRunNowControl
                researchReportSection

                if viewMode == .list {
                    checklistSection

                    aiSummaryCollapsible

                    // Discussion: the always-on in-ticket Q&A thread (composer + notes).
                    // Available in every column — clarifying questions shouldn't sit
                    // behind a toggle.
                    Divider().opacity(0.5)
                    discussionSection

                    // Proposed outreach sits directly under the discussion: it is
                    // the one thing on the ticket that asks the reader for a
                    // decision with an outside effect.
                    outreachSection

                    if !attachments.isEmpty {
                        attachmentsSection
                    }

                    // History: rounds + audit trail — the background (prior rounds, who
                    // moved what, what got fixed). Collapsed by default so the active
                    // work (checklist + feedback + discussion) leads.
                    Divider().opacity(0.5)
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

                ticketDates
            }
            .padding(24)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                if isAddingAutoPRContext {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(autoPRContextInstructions)
                            .font(.ticket(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                        noteComposer
                    }
                    .padding(16)
                    .background(Color.appBackground)
                    .overlay(alignment: .top) { Divider() }
                }
                if isRejecting {
                    ScrollView { rejectEditor.padding(16) }
                        .frame(maxHeight: 260)
                        .overlay(alignment: .top) { Divider() }
                } else if task.boardColumn == "review" {
                    reviewFooter
                }
            }
            .background(Color.appBackground)
        }
        .frame(width: viewMode == .graph ? 820 : 700)
        .frame(maxHeight: 820)
        .background(Color.appBackground)
        .task {
            // Ensure the per-user updates store is bound to this ticket's
            // project (idempotent if the board already configured it; corrects
            // it if the viewer was opened from a non-board surface).
            TicketUpdatesStore.shared.configure(
                userId: appState.currentUser?.id, projectId: viewModel.project?.id)
            // Always refresh on open. The board bundle may have cached the
            // empty pre-run attachment list; a research report is uploaded
            // before AutoPR's later task-update event, and that event does not
            // embed files. Reusing the cache here made a finished report look
            // as though it had no viewer until the whole board was reloaded.
            await viewModel.loadTaskFiles(taskId: task.id)
            await viewModel.loadSubtasks(taskId: task.id)
            // Refresh commit-driven suggestions so chips appear even when the
            // ticket is opened straight from the board (no-op if no repo bound).
            await viewModel.loadCommitSuggestions()
            // In review, load which commit completed each done item so the
            // reviewer can audit (and overturn) the AI auto-checks.
            if task.boardColumn == "review" {
                await viewModel.loadCommitCompletions(taskId: task.id)
            }
            // Discussion is always shown, so load history once on open to
            // populate the notes thread (and the collapsed rounds feed).
            if !historyLoaded { await loadHistory() }
            // Research cards are the only ones that carry proposals today, but
            // ask on every ticket: the answer is an empty list and the section
            // renders nothing.
            await loadStagedActions()
            // This one response owns the bot identity, watched-board state,
            // and research grant. Load it for every ticket so attribution and
            // queue labels are trustworthy even outside the board surface.
            await loadResearchGrant()
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

    private var ticketToolbar: some View {
        HStack(spacing: 16) {
            HStack(spacing: 2) {
                modeButton(.list, icon: "list.bullet")
                modeButton(.graph, icon: "point.3.connected.trianglepath.dotted")
            }
            .padding(2)
            .background(appState.themeText.opacity(0.08))
            .cornerRadius(5)
            Spacer()
            Button("Edit") { onEdit() }
                .buttonStyle(.plain)
                .font(.ticket(size: 11))
                .help("Edit this ticket")
            if isCopying || isDuplicating || isSummarizing {
                ProgressView().controlSize(.small)
            }
            Menu {
                Button {
                    Task { await copyTicketToClipboard() }
                } label: {
                    Label(didCopy ? "Copied" : "Copy ticket", systemImage: "doc.on.doc")
                }
                .buttonStyle(.plain)
                .disabled(isCopying)
                .help("Copy ticket as text + screenshot paths (for Claude Code)")
                Button {
                    Task {
                        isDuplicating = true
                        await viewModel.duplicateTask(task)
                        isDuplicating = false
                        didDuplicate = true
                        try? await Task.sleep(for: .milliseconds(1500))
                        didDuplicate = false
                    }
                } label: {
                    Label(didDuplicate ? "Duplicated" : "Duplicate ticket", systemImage: "plus.square.on.square")
                }
                .buttonStyle(.plain)
                .disabled(isDuplicating)
                .help("Duplicate this ticket")
                Button {
                    Task {
                        isSummarizing = true
                        await viewModel.summarizeTask(taskId: task.id, projectId: task.projectId)
                        isSummarizing = false
                        // Auto-expand the (otherwise collapsed) AI Summary so the
                        // user sees the result of their click.
                        withAnimation(.easeInOut(duration: 0.18)) { showSummary = true }
                    }
                } label: {
                    Label("Summarize with AI", systemImage: "sparkles")
                }
                .buttonStyle(.plain)
                .disabled(isSummarizing)
                .help("AI catch-up summary — where it's at, what's been done (Gemini)")
            } label: {
                Image(systemName: "ellipsis").frame(width: 24, height: 24)
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            .help("More ticket actions")
            .accessibilityLabel("More ticket actions")
            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.ticket(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Close ticket")
            .accessibilityLabel("Close ticket")
        }
    }

    private var reviewFooter: some View {
        HStack(spacing: 12) {
            if task.boardColumn == "review" && !isRejecting {
                Button {
                    isRejecting = true
                    rejectNote = ""
                } label: {
                    Label("Send back", systemImage: "arrow.uturn.backward")
                        .font(.ticket(size: 12))
                        .foregroundColor(.mwAttention)
                }
                .buttonStyle(.plain)
                .help("Mark incomplete and send to Changes Requested — notifies the assignee")

                Button {
                    isApproving = true
                } label: {
                    Label("Approve", systemImage: "checkmark.seal")
                        .font(.ticket(size: 12))
                        .foregroundColor(.mwInkStrong)
                }
                .buttonStyle(.plain)
                .help("Approve out of review → Done, with a sign-off")
                .popover(isPresented: $isApproving, arrowEdge: .top) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Approve & close")
                            .font(.ticket(size: 11)).foregroundColor(appState.themeText)
                        TextField("Optional sign-off note…", text: $approveNote, axis: .vertical)
                            .textFieldStyle(.plain).font(.ticket(size: 12)).foregroundColor(appState.themeText)
                            .lineLimit(1...3).padding(8).background(appState.themeText.opacity(0.08)).cornerRadius(6)
                        HStack {
                            Spacer()
                            Button("Cancel") {
                                isApproving = false
                                approveNote = ""
                            }
                            .buttonStyle(.plain).font(.ticket(size: 11)).foregroundColor(.secondary)
                            Button("Approve") {
                                Task { await submitApprove() }
                            }
                            .buttonStyle(.plain).font(.ticket(size: 11))
                            .foregroundColor(.white).padding(.horizontal, 10).padding(.vertical, 4)
                            .background(Color.mwSolid).cornerRadius(5)
                        }
                    }
                    .padding(12).frame(width: 260)
                    .background(appState.themeCard)
                }
            }
            Spacer()
            Text("Ready for your review").font(.ticket(size: 11)).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 24).padding(.vertical, 14)
        .overlay(alignment: .top) { Divider().opacity(0.5) }
    }

    func metaPill(label: String, color: Color) -> some View {
        Text(label)
            .font(.ticket(size: 11))
            .foregroundColor(color)

    }
}
