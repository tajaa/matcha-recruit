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

    /// A short, human-readable state for the ticket detail banner. The full
    /// machine-written note remains visible below it, including build/PR/card
    /// identifiers, so this is a summary rather than a lossy replacement.
    var autoSetupStatus: (label: String, color: Color, icon: String) {
        let note = (autoSetupProgressNote ?? "").lowercased()
        if note.contains("awaiting answers") || note.contains("answers needed") {
            return ("AWAITING ANSWERS", .orange, "questionmark.circle.fill")
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

    /// Persistent provenance shown directly below the ticket metadata. Unlike
    /// the one-line card preview, this deliberately renders the full note so a
    /// reviewer can see the exact AutoPR decision after opening the card.
    @ViewBuilder
    var autoSetupBanner: some View {
        if let note = autoSetupProgressNote {
            let status = autoSetupStatus
            if appState.isGraphite {
                VStack(alignment: .leading, spacing: 6) {
                    asciiRule("AUTO SETUP · \(status.label)")
                    Text(note)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(appState.themeText)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                    autoPRReconsiderationControl
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: status.icon)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(status.color)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("AUTO SETUP · \(status.label)")
                            .font(.system(size: 10, weight: .bold))
                            .tracking(0.6)
                            .foregroundColor(status.color)
                        Text(note)
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeText.opacity(0.8))
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                        autoPRReconsiderationControl
                    }
                }
                .padding(.vertical, 10)
                .padding(.horizontal, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(status.color.opacity(0.08))
                .cornerRadius(8)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(status.color.opacity(0.24), lineWidth: 1))
            }
        }
    }

    var canRequestAutoPRReconsideration: Bool {
        guard let note = autoSetupProgressNote else { return false }
        let liveTask = liveAutoPRTask
        let normalizedNote = note.lowercased()
        let isAwaitingAnswers = note.hasPrefix("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS")
            || (normalizedNote.hasPrefix("from auto setup") && normalizedNote.contains("answers needed"))
        let isNoSafeAction = note.contains("[autopr:no-spec ")
            && ["already_fixed", "migration_required", "policy_blocked", "external_dependency"]
                .contains(where: note.contains)
        return liveTask.status != "cancelled"
            && ["todo", "changes_requested"].contains(liveTask.boardColumn)
            && (isAwaitingAnswers || isNoSafeAction)
    }

    var autoPRReconsiderationIsPending: Bool {
        let liveTask = liveAutoPRTask
        let submittedDecisionIsCurrent = didSubmitAutoPRContext
            && liveTask.progressNote == task.progressNote
        return submittedDecisionIsCurrent || liveTask.autoprReconsiderationPending == true
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

    @ViewBuilder
    var autoPRRunNowControl: some View {
        if canRequestAutoPRRun {
            HStack(spacing: 8) {
                if autoPRRunIsQueued {
                    Label("Queued for AutoPR", systemImage: "bolt.horizontal.circle.fill")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.mwInkStrong)
                } else {
                    Button {
                        Task { await requestAutoPRRun() }
                    } label: {
                        Label(
                            requestingAutoPRRun ? "Queueing…" : "Run AutoPR now",
                            systemImage: "bolt.fill"
                        )
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.mwInkStrong)
                    }
                    .buttonStyle(.plain)
                    .disabled(requestingAutoPRRun)
                    .help("Queue this ticket for the next AutoPR tick instead of the twenty-minute sweep")
                }
                if let error = autoPRRunError {
                    Text(error)
                        .font(.system(size: 10))
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
                        .font(.system(size: 10, weight: .semibold))
                    Text("Reconsideration queued")
                        .font(.system(size: 10, weight: .semibold))
                }
                .foregroundColor(.mwInkStrong)
                .padding(.top, 3)
            } else if isAddingAutoPRContext {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Explain what AutoPR missed or attach evidence. Use --draft-pr to require a draft, --trust-still-broken to reject another already-fixed result, and --test-route=/app/... for a test-tenant replay.")
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeTextSecondary)
                    noteComposer
                }
                .padding(.top, 3)
            } else {
                Button {
                    replyingToNote = nil
                    autoPRContextError = nil
                    isAddingAutoPRContext = true
                    Task { @MainActor in isNoteFieldFocused = true }
                } label: {
                    Label("Add additional context", systemImage: "arrowshape.turn.up.left")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.mwInkStrong)
                }
                .buttonStyle(.plain)
                .padding(.top, 3)
                .help("Give AutoPR new evidence and ask it to reconsider this decision")
            }
        }
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
        return HStack(spacing: 8) {
            HStack(spacing: 4) {
                Image(systemName: p.icon).font(.system(size: 9, weight: .semibold))
                Text(p.label).font(.system(size: 10, weight: .semibold))
            }
            .foregroundColor(p.color)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(p.color.opacity(0.14)).cornerRadius(4)

            metaPill(label: task.priority.capitalized, color: .secondary)
            if let due = task.dueDate, !due.isEmpty {
                metaPill(label: "Due \(String(due.prefix(10)))", color: .secondary)
            }
            assigneeMenu
            if currentRound > 0 {
                Text("Round \(currentRound)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
            }
            if let days = daysInReview {
                HStack(spacing: 2) {
                    Image(systemName: "clock").font(.system(size: 8))
                    Text(days <= 0 ? "review today" : "review \(days)d")
                        .font(.system(size: 9, weight: .medium))
                }
                .foregroundColor(days >= 3 ? .mwAttention : .secondary)
            }
            if let elName = task.elementName
                ?? viewModel.elements.first(where: { $0.id == task.elementId })?.name {
                HStack(spacing: 3) {
                    Image(systemName: "square.stack.3d.up.fill").font(.system(size: 8))
                    Text(elName).font(.system(size: 9, weight: .semibold))
                }
                .foregroundColor(.mwInkStrong)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Color.mwInkStrong.opacity(0.15)).cornerRadius(3)
            }
            Spacer(minLength: 0)
        }
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
           let pn = task.progressNote?.trimmingCharacters(in: .whitespacesAndNewlines), !pn.isEmpty {
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
            VStack(alignment: .leading, spacing: 8) {
                heroRule(color: .mwInkStrong, icon: "magnifyingglass.circle.fill",
                         label: "DO NOW · REVIEW",
                         text: "Assess this submission, then Approve or Send back below.")
                reviewDeltaSection
            }
        case .progress(let pn):
            heroRule(color: .mwInkStrong, icon: "hammer.fill", label: "WHERE WE'RE AT", text: pn)
        case .done:
            heroRule(color: .mwInkStrong, icon: "checkmark.seal.fill", label: "DONE", text: "This ticket is closed.")
        case .brief(let desc):
            // No more-specific directive (fresh/no-note ticket) → the brief is
            // the directive. Phase-colored so it still reads as the current state.
            heroRule(color: currentPhase.color, icon: "doc.text", label: "THE BRIEF", text: desc)
        case .phase:
            // No feedback, no progress note, no description → don't leave a blank
            // hole; show the phase + owner so the sheet still answers "where is
            // this and whose move is it?" (the old stateBanner's job).
            heroRule(color: currentPhase.color, icon: currentPhase.icon,
                     label: currentPhase.label.uppercased(),
                     text: currentPhase.owner.isEmpty ? "No details yet." : currentPhase.owner)
        }
    }

    // MARK: - Hero chrome

    /// `── LABEL ─────────` monospace rule — the graphite ASCII section header,
    /// stretching to fill the row. Used by the hero + collapsibles in graphite.
    func asciiRule(_ label: String) -> some View {
        HStack(spacing: 8) {
            Text("──")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(appState.themeTextSecondary)
            Text(label.uppercased())
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundColor(appState.themeTextSecondary)
                .tracking(1).fixedSize()
            Rectangle().fill(appState.themeBorder).frame(height: 1)
        }
    }

    /// Prominent hero. Graphite: a flat ASCII rule + text (no tinted box) for the
    /// stripped-down terminal feel. Other themes: the left-rule card.
    @ViewBuilder
    func heroRule(color: Color, icon: String, label: String, text: String) -> some View {
        if appState.isGraphite {
            VStack(alignment: .leading, spacing: 6) {
                asciiRule(label)
                Text(text)
                    .font(.system(size: 13))
                    .foregroundColor(appState.themeText)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            HStack(alignment: .top, spacing: 10) {
                RoundedRectangle(cornerRadius: 1.5).fill(color.opacity(0.85)).frame(width: 3)
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 5) {
                        Image(systemName: icon).font(.system(size: 11, weight: .semibold))
                        Text(label).font(.system(size: 10, weight: .bold)).tracking(0.6)
                    }
                    .foregroundColor(color)
                    Text(text)
                        .font(.system(size: 13))
                        .foregroundColor(appState.themeText)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.vertical, 10).padding(.horizontal, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(color.opacity(0.06)).cornerRadius(8)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(color.opacity(0.18), lineWidth: 1))
        }
    }

    /// Changes-requested hero — the send-back note promoted to the focal point,
    /// with the per-item denials (severity + reason) the reviewer flagged.
    /// Absorbs the old NEEDS WORK block.
    ///
    /// `reviewDenials` walks the whole history, so it is bound ONCE here and
    /// threaded into the severity summary — the previous shape recomputed it
    /// four times per body render (twice inside `denialSeverityCounts` alone).
    @ViewBuilder
    func feedbackHero(_ fb: String) -> some View {
        let denials = reviewDenials
        let counts = denialSeveritySummary(denials)
        if appState.isGraphite {
            // Flat ASCII — no tinted box, monochrome denials with `!` markers.
            VStack(alignment: .leading, spacing: 6) {
                asciiRule("DO NOW · CHANGES REQUESTED")
                Text(fb)
                    .font(.system(size: 13)).foregroundColor(appState.themeText)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                if let counts {
                    Text(counts).font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .foregroundColor(appState.themeText.opacity(0.6))
                }
                ForEach(Array(denials.enumerated()), id: \.offset) { _, d in
                    HStack(alignment: .top, spacing: 6) {
                        Text(d.severity == "blocker" ? "[!]" : "[ ]")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(appState.themeTextSecondary)
                        Text("\(d.title)\(d.reason.isEmpty ? "" : " — \(d.reason)")")
                            .font(.system(size: 11)).foregroundColor(appState.themeText.opacity(0.75))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            let color = Color.mwAttention
            HStack(alignment: .top, spacing: 10) {
                RoundedRectangle(cornerRadius: 1.5).fill(color.opacity(0.85)).frame(width: 3)
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 5) {
                        Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 11, weight: .semibold))
                        Text("DO NOW · CHANGES REQUESTED").font(.system(size: 10, weight: .bold)).tracking(0.5)
                    }
                    .foregroundColor(color)
                    Text(fb)
                        .font(.system(size: 13))
                        .foregroundColor(appState.themeText)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                    if let counts {
                        Text(counts).font(.system(size: 9, weight: .semibold)).foregroundColor(appState.themeText.opacity(0.6))
                    }
                    ForEach(Array(denials.enumerated()), id: \.offset) { _, d in
                        HStack(alignment: .top, spacing: 5) {
                            Image(systemName: "xmark.square.fill").font(.system(size: 9)).foregroundColor(color.opacity(0.9))
                            if !d.severity.isEmpty {
                                Text(d.severity.uppercased())
                                    .font(.system(size: 7, weight: .bold)).tracking(0.3)
                                    .foregroundColor(d.severity == "blocker" ? .mwAttention : .secondary)
                                    .padding(.horizontal, 3).padding(.vertical, 1)
                                    .background((d.severity == "blocker" ? Color.mwAttention : Color.secondary).opacity(0.15))
                                    .cornerRadius(2)
                            }
                            Text("\(d.title)\(d.reason.isEmpty ? "" : " — \(d.reason)")")
                                .font(.system(size: 11)).foregroundColor(appState.themeText.opacity(0.75))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .padding(.vertical, 10).padding(.horizontal, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(color.opacity(0.06)).cornerRadius(8)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(color.opacity(0.18), lineWidth: 1))
        }
    }
}
