import SwiftUI

// MARK: - Header: phase, meta line, and the one directive hero
//
// Split out of TaskViewerSheet+Sections.swift. Everything here answers
// "where is this ticket and what should I do about it right now?".

extension TaskViewerSheet {

    // MARK: - Automation provenance

    /// The sheet is opened with a task snapshot, while project WebSocket
    /// updates continue to mutate the view model. AutoPR state must follow the
    /// live row so a completed reconsideration does not remain visually queued
    /// until the sheet is closed and reopened.
    var liveAutoPRTask: MWProjectTask {
        viewModel.tasks.first(where: { $0.id == task.id }) ?? task
    }

    var autoPRIsQueueCandidate: Bool {
        liveAutoPRTask.isAutoPRQueueCandidate(
            botUserId: viewModel.autoPRBotUserId,
            boardIsWatched: viewModel.autoPRBoardIsWatched
        )
    }

    /// AutoPR writes its durable ticket state into `progress_note`. The board
    /// card already previews that field, but the detail sheet must repeat it:
    /// opening a ticket should never hide the fact that an autonomous system
    /// selected it, nor the reason it did or did not create a PR.
    var autoSetupProgressNote: String? {
        let note = liveAutoPRTask.progressNote?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard note.hasPrefix("🤖 AUTO SETUP") || note.lowercased().hasPrefix("from auto setup") else {
            return nil
        }
        return note
    }

    var autoPRIsAwaitingAnswers: Bool {
        guard let note = autoSetupProgressNote else { return false }
        let normalized = note.lowercased()
        // publish.sh still recognizes the legacy lowercase note, whose state
        // segment reads "awaiting answers" and never "answers needed".
        return note.hasPrefix("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS")
            || (normalized.hasPrefix("from auto setup")
                && (normalized.contains("answers needed")
                    || normalized.contains("awaiting answers")))
    }

    var autoPRNeedsRuntimeApproval: Bool {
        guard let note = autoSetupProgressNote else { return false }
        // The RUNTIME APPROVAL REQUIRED spelling is the pre-rename header;
        // cards paused before the rename still carry it.
        return note.hasPrefix("🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES")
            || note.hasPrefix("🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED")
    }

    /// A short, human-readable state for the ticket detail banner. The full
    /// machine-written note remains available in its disclosure, including
    /// build/PR/card identifiers, so this is a summary rather than a lossy replacement.
    var autoSetupStatus: (label: String, color: Color, icon: String) {
        if liveAutoPRTask.autoprPaused == true {
            return ("AUTOPR PAUSED", .orange, "pause.circle.fill")
        }
        if liveAutoPRTask.autoprClaimedAt != nil {
            return ("WORKING NOW", .mwInkStrong, "hammer.circle.fill")
        }
        let note = (autoSetupProgressNote ?? "").lowercased()
        if autoPRNeedsRuntimeApproval {
            return ("APPROVAL NEEDED FOR 10 MORE MINUTES", .orange, "timer")
        }
        if autoPRIsAwaitingAnswers {
            return ("AWAITING ANSWERS", .orange, "questionmark.circle.fill")
        }
        if autoPRIsQueueCandidate {
            return ("IN QUEUE", .blue, "clock.arrow.circlepath")
        }
        if note.contains("already fixed") {
            return ("NO PR · ALREADY FIXED", .mwInkStrong, "checkmark.circle.fill")
        }
        if note.contains("migration required") {
            return ("NO PR · MIGRATION REQUIRED", .orange, "cylinder.split.1x2.fill")
        }
        if note.contains("policy blocked") || note.contains("external dependency") {
            return ("BLOCKED", .orange, "exclamationmark.triangle.fill")
        }
        if note.contains("merged") || note.contains("ready for review") {
            return ("READY FOR REVIEW", .mwInkStrong, "arrow.right.circle.fill")
        }
        return ("AUTOMATION IN PROGRESS", .mwInkStrong, "cpu")
    }

    /// Persistent automation provenance. The outcome stays readable at a
    /// glance; machine details and any original message are opt-in so this does
    /// not become a second giant body competing with the contributor's brief.
    @ViewBuilder
    var autoSetupBanner: some View {
        if let note = autoSetupProgressNote {
            let status = autoSetupStatus
            let paragraphs = note.components(separatedBy: "\n\n").filter { !$0.isEmpty }
            let first = paragraphs.first ?? note
            let summary = first.range(of: " · note: ").map { String(first[$0.upperBound...]) } ?? first
            let hasTransientRunState = liveAutoPRTask.autoprClaimedAt != nil
                || (autoPRIsQueueCandidate
                    && !autoPRNeedsRuntimeApproval
                    && !autoPRIsAwaitingAnswers)
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Image(systemName: "cpu").foregroundColor(status.color)
                    Text("matcha-autopr").foregroundColor(appState.themeText)
                    Text("Automated").foregroundStyle(.secondary)
                    Spacer(minLength: 8)
                    Label(status.label == "AWAITING ANSWERS" ? "Your input is needed" : status.label.capitalized,
                          systemImage: status.icon)
                        .foregroundColor(status.color)
                }
                .font(.ticket(size: 11))
                Text(hasTransientRunState ? "Previous AutoPR update: \(summary)" : summary)
                    .font(.ticket(size: 12)).lineSpacing(3)
                    .foregroundColor(appState.themeTextSecondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                if autoPRIsAwaitingAnswers {
                    ForEach(Array(paragraphs.dropFirst().enumerated()), id: \.offset) { _, paragraph in
                        Text(paragraph)
                            .font(.ticket(size: 12))
                            .lineSpacing(3)
                            .foregroundColor(appState.themeText)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(status.color.opacity(0.08))
                            .cornerRadius(5)
                    }
                }
                autoPRReconsiderationControl
                DisclosureGroup(paragraphs.count > 1 ? "Technical details & original message" : "Technical details") {
                    Text(note).font(.system(size: 11, design: .monospaced))
                        .textSelection(.enabled).padding(.top, 8)
                }
                .font(.ticket(size: 11)).foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else if liveAutoPRTask.autoprClaimedAt != nil
                    || autoPRIsQueueCandidate {
            let isWorking = liveAutoPRTask.autoprClaimedAt != nil
            HStack(spacing: 8) {
                Image(systemName: "cpu")
                Text("matcha-autopr").foregroundColor(appState.themeText)
                Text("Automated").foregroundStyle(.secondary)
                Spacer(minLength: 8)
                Label(isWorking ? "Working now" : "In queue",
                      systemImage: isWorking ? "hammer" : "clock")
                    .foregroundColor(isWorking ? .mwInkStrong : .blue)
            }
            .font(.ticket(size: 11))
            .foregroundStyle(.secondary)
        }
    }

    var canRequestAutoPRReconsideration: Bool {
        guard let note = autoSetupProgressNote else { return false }
        let liveTask = liveAutoPRTask
        let isNoSafeAction = note.contains("[autopr:no-spec ")
            // Mirror of the server's _AUTOPR_NO_SPEC_RE alternation.
            && ["already_fixed", "acceptance_criteria_met", "migration_required",
                "policy_blocked", "external_dependency", "needs_clarification"]
                .contains(where: note.contains)
        return liveTask.status != "cancelled"
            && ["todo", "changes_requested"].contains(liveTask.boardColumn)
            && (autoPRIsAwaitingAnswers || autoPRNeedsRuntimeApproval || isNoSafeAction)
    }

    var autoPRReconsiderationIsPending: Bool {
        let liveTask = liveAutoPRTask
        let submittedDecisionIsCurrent = didSubmitAutoPRContext
            && liveTask.progressNote == task.progressNote
        return liveTask.autoprPaused != true
            && (submittedDecisionIsCurrent || liveTask.autoprReconsiderationPending == true)
    }

    // MARK: - Run AutoPR now

    /// The scheduled Kanban lane sweeps every twenty minutes. This is the way
    /// past that clock for one specific ticket: the local watcher polls for
    /// pending requests once a minute and dispatches a run as soon as it sees
    /// one. Only the two lanes AutoPR actually picks from can queue.
    var canRequestAutoPRRun: Bool {
        let liveTask = liveAutoPRTask
        return liveTask.status != "cancelled"
            && ["todo", "changes_requested"].contains(liveTask.boardColumn)
    }

    /// `didRequestAutoPRRun` only bridges the gap between the POST and the
    /// reload that follows it; `requestAutoPRRun` clears it again, so the live
    /// row is what actually decides. A request also has a server-side shelf
    /// life, which is what lets this chip clear itself if a run never claims it.
    var autoPRRunIsQueued: Bool {
        didRequestAutoPRRun || liveAutoPRTask.autoprRunRequestedAt != nil
    }

    /// "HTTP 409: AutoPR does not watch this board…" — the sentence after
    /// the colon is the part a person can act on.
    static func stripHTTPPrefix(_ message: String) -> String {
        guard message.hasPrefix("HTTP "), let colon = message.firstIndex(of: ":") else { return message }
        return message[message.index(after: colon)...].trimmingCharacters(in: .whitespaces)
    }

    /// Same endpoint and same queue; a research card just produces a report
    /// under the attachments instead of a draft PR, so say so on the button.
    var autoPRRunNowLabel: String {
        KanbanTemplate.from(category: liveAutoPRTask.category)?.autoprRunNowLabel ?? "Run AutoPR now"
    }

    /// The board grant this card's kind needs; nil for ordinary PR cards.
    var autoPRArtifactCapability: String? {
        KanbanTemplate.from(category: liveAutoPRTask.category)?.autoprArtifactCapability
    }

    /// Why the run button is disabled, when it is. No card can run on an
    /// unwatched board; Research also requires its explicit capability grant.
    var autoPRRunBlockedReason: String? {
        if viewModel.autoPRBoardIsWatched == false {
            return "AutoPR does not watch this board, so this card cannot run."
        }
        guard let capability = autoPRArtifactCapability else { return nil }
        if researchGranted == false {
            return "This board is not granted \(capability). An admin can grant it under Admin → Settings → AutoPR board capabilities."
        }
        return nil
    }

    func loadResearchGrant() async {
        guard let pid = viewModel.project?.id else { return }
        do {
            let caps = try await MatchaWorkService.shared.autoprBoardCapabilities(projectId: pid)
            researchGranted = caps.has(autoPRArtifactCapability ?? "research", on: pid)
            viewModel.autoPRBotUserId = caps.autoprBotUserId
            viewModel.autoPRBoardIsWatched = caps.isWatched(pid)
        } catch {
            // Unknown stays unknown: the button works as before and the
            // server / harness give the definitive answer.
            researchGranted = nil
        }
    }

    @ViewBuilder
    var autoPRRunNowControl: some View {
        let hasActiveClaim = liveAutoPRTask.autoprClaimedAt != nil
        let canControlRun = canRequestAutoPRRun
            || hasActiveClaim
            || liveAutoPRTask.autoprPaused == true
        if canControlRun {
            HStack(spacing: 8) {
                if liveAutoPRTask.autoprPaused == true {
                    Label("AutoPR paused", systemImage: "pause.circle")
                        .font(.ticket(size: 10))
                    if let reason = liveAutoPRTask.autoprHoldReason, !reason.isEmpty {
                        Text(reason)
                            .font(.ticket(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                            .help(reason)
                    }
                    if canRequestAutoPRRun {
                        Button("Run again") { Task { await requestAutoPRRun() } }
                            .buttonStyle(.plain)
                            .disabled(requestingAutoPRRun || addingNote)
                    } else {
                        Text("Move to Todo or Changes Requested to run again.")
                            .font(.ticket(size: 10))
                            .foregroundColor(.secondary)
                    }
                } else if hasActiveClaim {
                    Label("AutoPR working", systemImage: "hammer.circle.fill")
                        .font(.ticket(size: 10))
                        .foregroundColor(.mwInkStrong)
                    Button(requestingAutoPRRun ? "Pausing…" : "Pause retries") {
                        Task { await cancelAutoPRRun() }
                    }
                    .buttonStyle(.plain)
                    .font(.ticket(size: 11))
                    .disabled(requestingAutoPRRun || addingNote)
                    .help("Prevent automatic retries. A run already executing may still finish.")
                } else if autoPRRunIsQueued || autoPRReconsiderationIsPending {
                    Label("Queued for AutoPR", systemImage: "bolt.horizontal.circle.fill")
                        .font(.ticket(size: 10))
                        .foregroundColor(.mwInkStrong)
                } else if let reason = autoPRRunBlockedReason {
                    Label(autoPRRunNowLabel, systemImage: "bolt.slash")
                        .font(.ticket(size: 10))
                        .foregroundColor(.secondary)
                        .help(reason)
                    Text(reason)
                        .font(.ticket(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                } else {
                    Button {
                        Task { await requestAutoPRRun() }
                    } label: {
                        Label(
                            requestingAutoPRRun ? "Queueing…" : autoPRRunNowLabel,
                            systemImage: "bolt.fill"
                        )
                        .font(.ticket(size: 10))
                        .foregroundColor(.mwInkStrong)
                    }
                    .buttonStyle(.plain)
                    .disabled(requestingAutoPRRun || addingNote)
                    .help("Queue this ticket for the next AutoPR tick instead of the twenty-minute sweep")
                    // A plain Todo / Changes Requested card had no way to be
                    // parked: Unqueue only appears once a run is requested.
                    Button(requestingAutoPRRun ? "Holding…" : "Hold") {
                        Task { await cancelAutoPRRun() }
                    }
                    .buttonStyle(.plain)
                    .font(.ticket(size: 11))
                    .disabled(requestingAutoPRRun || addingNote)
                    .help("Hold this ticket so AutoPR skips it until you press Run again")
                }
                if (autoPRRunIsQueued || autoPRReconsiderationIsPending) && liveAutoPRTask.autoprPaused != true {
                    Button(requestingAutoPRRun ? "Unqueueing…" : "Unqueue") {
                        Task { await cancelAutoPRRun() }
                    }
                    .buttonStyle(.plain)
                    .font(.ticket(size: 11))
                    .disabled(requestingAutoPRRun || addingNote)
                    .help("Hold future runs while you edit.")
                }
                if let error = autoPRRunError {
                    Text(Self.stripHTTPPrefix(error))
                        .font(.ticket(size: 10))
                        .foregroundColor(.red)
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    var autoPRReconsiderationControl: some View {
        if canRequestAutoPRReconsideration {
            if autoPRReconsiderationIsPending {
                HStack(spacing: 5) {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.ticket(size: 10))
                    Text("Reconsideration queued")
                        .font(.ticket(size: 10))
                }
                .foregroundColor(.mwInkStrong)
                .padding(.top, 3)
            } else if isAddingAutoPRContext {
                Text("Answer below — you can scroll the questions while writing.")
                    .font(.ticket(size: 10))
                    .foregroundColor(.secondary)
            } else {
                Button {
                    replyingToNote = nil
                    autoPRContextError = nil
                    if autoPRNeedsRuntimeApproval {
                        newNote = "--extend-runtime"
                    }
                    autoPRContextExpectedNote = autoSetupProgressNote
                    isAddingAutoPRContext = true
                    Task { @MainActor in isNoteFieldFocused = true }
                } label: {
                    Label(autoPRContextActionLabel, systemImage: "arrowshape.turn.up.left")
                        .font(.ticket(size: 10))
                        .foregroundColor(.mwInkStrong)
                }
                .buttonStyle(.plain)
                .padding(.top, 3)
                .help("Give AutoPR new evidence and ask it to reconsider this decision")
            }
        }
    }

    var autoPRContextActionLabel: String {
        if autoPRNeedsRuntimeApproval { return "Approve 10 more minutes" }
        if autoPRIsAwaitingAnswers { return "Answer AutoPR questions" }
        return "Add additional context"
    }

    var autoPRContextInstructions: String {
        if autoPRNeedsRuntimeApproval {
            return "Keep --extend-runtime in this reply to approve 10 more minutes. AutoPR will continue from its saved work."
        }
        if autoPRIsAwaitingAnswers {
            return "Answer in your own words, add context, or tell AutoPR what to research. It will use that guidance to continue the work. Numbered choices are optional."
        }
        return "Explain what AutoPR missed or attach evidence. Use --draft-pr to require a draft, --trust-still-broken to reject another already-fixed result, and --test-route=/app/... for a test-tenant replay."
    }

    // MARK: - "You are here" phase

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
            return StatePhase(label: "Changes Requested", owner: "Assignee to address feedback", color: .mwAttention, icon: "arrow.uturn.backward.circle.fill")
        }
        switch task.boardColumn {
        case "todo":
            return StatePhase(label: "Not Started", owner: "Assignee to begin", color: .secondary, icon: "circle.dashed")
        case "in_progress":
            return StatePhase(label: "In Progress", owner: "Assignee working", color: .mwInkStrong, icon: "hammer.fill")
        case "review":
            return StatePhase(label: "In Review", owner: "Reviewer to assess", color: .mwInkStrong, icon: "magnifyingglass.circle.fill")
        case "changes_requested":
            return StatePhase(label: "Changes Requested", owner: "Assignee to address feedback", color: .mwAttention, icon: "arrow.uturn.backward.circle.fill")
        case "done":
            return StatePhase(label: "Done", owner: "Closed", color: .mwInkStrong, icon: "checkmark.seal.fill")
        default:
            return StatePhase(label: columnLabel, owner: "", color: .secondary, icon: "circle")
        }
    }

    // (Former `stateBanner` removed — folded into `metaLine` during the
    // action-first reorg; `currentPhase`/`StatePhase` above are still used.)

    // MARK: - Time in review (#9b)

    /// Whole days the ticket has sat in review (from its last move). Nil when not
    /// in review or the timestamp doesn't parse.
    var daysInReview: Int? {
        guard task.boardColumn == "review", let moved = task.lastMovedAt else { return nil }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let d = iso.date(from: moved) ?? ISO8601DateFormatter().date(from: moved) else { return nil }
        return Calendar.current.dateComponents([.day], from: d, to: Date()).day
    }

    // MARK: - Reorganized header: one meta line, one directive hero

    /// Single status line — folds the old status/priority pills AND the
    /// "YOU ARE HERE" banner into one row so the top of the sheet isn't three
    /// stacked status blocks. Phase (colored) · priority · assignee · round ·
    /// time-in-review.
    var metaLine: some View {
        let p = currentPhase
        return FlowLayout(spacing: 12) {
            Label(p.label, systemImage: p.icon).foregroundColor(p.color)
            metaPill(label: task.priority.capitalized, color: .secondary)
            assigneeMenu
            if currentRound > 1 { Text("Round \(currentRound)") }
            if let days = daysInReview {
                Text(days <= 0 ? "Review today" : "In review \(days)d")
                    .foregroundColor(days >= 3 ? .mwAttention : .secondary)
            }
            if let due = task.dueDate, !due.isEmpty {
                Text("Due \(String(due.prefix(10)))")
            }
            if let name = task.elementName
                ?? viewModel.elements.first(where: { $0.id == task.elementId })?.name {
                Label(name, systemImage: "square.stack.3d.up")
                    .lineLimit(1).frame(maxWidth: 200, alignment: .leading)
            }
        }
        .font(.ticket(size: 11))
        .foregroundStyle(.secondary)
    }

    /// Audit timestamps are available without competing with status and ownership.
    var ticketDates: some View {
        FlowLayout(spacing: 8) {
            if let created = liveAutoPRTask.createdAt {
                Text("Added \(PacificDateFormatter.absolute(created) ?? created)")
            }
            if let moved = liveAutoPRTask.lastMovedAt,
               let label = PacificDateFormatter.absolute(moved) {
                Text("· Moved \(label)")
            }
        }
        .font(.ticket(size: 10))
        .foregroundStyle(.secondary)
    }

    // MARK: - The directive

    /// What the hero says, decided once. `directiveHero` renders it, `descriptionIsHero`
    /// asks whether the brief was consumed by it, and `reviewContext` reuses the
    /// `.feedback` gate — three call sites that used to hand-mirror the same `if`
    /// ladder and were kept in sync only by comment.
    enum Directive {
        /// Reviewer sent it back; payload is the trimmed review note.
        case feedback(String)
        case review
        /// In progress with a progress note; payload is the trimmed note.
        case progress(String)
        case done
        /// Nothing more specific applies — the description IS the directive.
        case brief(String)
        /// Nothing to say at all; fall back to phase + owner.
        case phase
    }

    var directive: Directive {
        let fb = task.reviewNote?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !fb.isEmpty, ["changes_requested", "in_progress", "todo"].contains(task.boardColumn) {
            return .feedback(fb)
        }
        if task.boardColumn == "review" { return .review }
        if task.boardColumn == "in_progress",
           let pn = task.progressNote?.trimmingCharacters(in: .whitespacesAndNewlines),
           !pn.isEmpty,
           !(pn.hasPrefix("🤖 AUTO SETUP") || pn.lowercased().hasPrefix("from auto setup")) {
            return .progress(pn)
        }
        if task.boardColumn == "done" { return .done }
        if let desc = task.description?.trimmingCharacters(in: .whitespacesAndNewlines), !desc.isEmpty {
            return .brief(desc)
        }
        return .phase
    }

    /// True when the description is used AS the directive hero — so the
    /// Description collapsible is skipped to avoid showing it twice.
    var descriptionIsHero: Bool {
        if case .brief = directive { return true }
        return false
    }

    /// THE one salient block: what to do right now, chosen by phase. A send-back
    /// is the directive when present; otherwise the review prompt, the progress
    /// note, or (fresh ticket) the brief. Everything else on the sheet is
    /// supporting detail below this.
    @ViewBuilder
    var directiveHero: some View {
        switch directive {
        case .feedback(let fb):
            feedbackHero(fb)
        case .review:
            reviewDeltaSection
        case .progress(let pn):
            heroRule(label: "Progress update", text: pn)
        case .done:
            EmptyView()
        case .brief(let desc):
            heroRule(
                label: "Contributor brief · \(contributorDisplayName)",
                text: desc
            )
        case .phase:
            // No feedback, no progress note, no description → don't leave a blank
            // hole; show the phase + owner so the sheet still answers "where is
            // this and whose move is it?" (the old stateBanner's job).
            heroRule(label: currentPhase.label,
                     text: currentPhase.owner.isEmpty ? "No details yet." : currentPhase.owner)
        }
    }

    // MARK: - Quiet section chrome

    func heroRule(label: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            TicketSectionHeading(title: label)
            TicketBriefText(text: text).foregroundColor(appState.themeText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Feedback stays prominent through its wording and amber cue, not a large panel.
    @ViewBuilder
    func feedbackHero(_ fb: String) -> some View {
        let denials = reviewDenials
        VStack(alignment: .leading, spacing: 8) {
            Label("Review feedback", systemImage: "arrow.uturn.backward")
                .font(.ticket(size: 11)).foregroundColor(.mwAttention)
            TicketBriefText(text: fb).foregroundColor(appState.themeText)
            if let counts = denialSeveritySummary(denials) {
                Text(counts).font(.ticket(size: 11)).foregroundStyle(.secondary)
            }
            ForEach(Array(denials.enumerated()), id: \.offset) { _, d in
                HStack(alignment: .top, spacing: 6) {
                    if !d.severity.isEmpty {
                        Text(d.severity.capitalized)
                            .foregroundColor(d.severity == "blocker" ? .mwAttention : .secondary)
                    }
                    Text("\(d.title)\(d.reason.isEmpty ? "" : " — \(d.reason)")")
                        .foregroundColor(appState.themeText)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(.ticket(size: 12))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
