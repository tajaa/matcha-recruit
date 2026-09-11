import SwiftUI

struct KanbanCardView: View {
    @Environment(AppState.self) private var appState
    let task: MWProjectTask
    let attachments: [MWProjectFile]
    var pipelineMode: Bool = false
    /// Element label resolved by the board (task.elementName from the list
    /// query, with a client-side fallback so freshly created/edited cards show
    /// it before the next full reload).
    var elementName: String? = nil
    /// Count of distinct subtasks a commit may have completed (pending accept).
    /// Drives the purple "commits may have finished N" badge on the card face.
    var pendingCommitCount: Int = 0
    var autoPRRuntimeApprovalInFlight = false
    var autoPRBotUserId: String?
    var autoPRBoardIsWatched: Bool?
    let onTap: () -> Void
    let onToggle: () -> Void
    let onMoveColumn: (String) -> Void
    let onApproveAutoPRRuntime: () -> Void

    @State private var hovering = false

    /// "Company · Contact" for the card face (pipeline mode); nil when neither set.
    private var contactDisplay: String? {
        let parts = [task.contactCompany, task.contactName]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var priorityColor: Color {
        switch task.priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .secondary
        }
    }

    private var currentColumnLabel: String {
        columnsFor(pipeline: pipelineMode).first(where: { $0.key == task.boardColumn })?.label ?? task.boardColumn
    }

    private var assigneeDisplay: String? { task.displayAssignee }

    /// Full-width state at the top of the card. Queue and pickup are different
    /// moments: a request waits in Todo, while a claim moves to In Progress.
    /// Naming both prevents a quiet one-line note state from being mistaken for
    /// ordinary contributor prose.
    private var autoPRBanner: (label: String, detail: String, icon: String, color: Color)? {
        if task.autoprPaused == true {
            return ("AutoPR paused", "Run again from the ticket", "pause.circle.fill", .orange)
        }
        if task.autoprClaimedAt != nil {
            return ("AutoPR working", "Picked up", "hammer.circle.fill", .mwInkStrong)
        }
        if task.isAutoPRQueueCandidate(
            botUserId: autoPRBotUserId,
            boardIsWatched: autoPRBoardIsWatched
        ) {
            return ("In queue", "Waiting for matcha-autopr", "clock.arrow.circlepath", .blue)
        }
        return nil
    }

    /// Pull the answer form out of AutoPR's progress note for the card face.
    private var autoPRQuestionPreview: String? {
        guard let note = task.progressNote?.trimmingCharacters(in: .whitespacesAndNewlines),
              note.lowercased().contains("awaiting answers") else { return nil }
        let marker = "Answers needed — reply below with the numbered choices:"
        guard let range = note.range(of: marker) else {
            return "Open this ticket to view and answer AutoPR's questions."
        }
        let questions = note[range.upperBound...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return questions.isEmpty ? nil : questions
    }

    private var autoPRRuntimeDetails: String? {
        // The RUNTIME APPROVAL REQUIRED spelling is the pre-rename header;
        // cards paused before the rename still carry it.
        guard let note = task.progressNote?.trimmingCharacters(in: .whitespacesAndNewlines),
              note.hasPrefix("🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES")
                || note.hasPrefix("🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED")
        else { return nil }
        let lines = note.split(separator: "\n", omittingEmptySubsequences: true)
        guard lines.count > 1 else {
            return "The last run stopped at its time limit. Its partial work is saved."
        }
        return lines.dropFirst().joined(separator: "\n")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let banner = autoPRBanner {
                HStack(spacing: 5) {
                    Image(systemName: banner.icon)
                    Text(banner.label)
                    Text("· \(banner.detail)")
                        .foregroundColor(appState.themeTextSecondary)
                    Spacer(minLength: 0)
                }
                .font(.espresso(size: 10))
                .foregroundColor(banner.color)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(banner.color.opacity(0.06))
                .overlay(alignment: .bottom) { Divider().opacity(0.35) }
                .help(task.autoprPaused == true
                      ? "Open the ticket to run again. A new review round also releases this hold."
                      : banner.detail)
            }
            // Header — checkbox + title. Staleness no longer tints the whole
            // band (the 18% red/orange wash read as mud on dark surfaces);
            // the aging signal lives in the footer's clock + tinted time.
            HStack(alignment: .top, spacing: 8) {
                // Pipeline deals use the Won/Lost outcome, not task completion —
                // the checkbox would shove the card into 'done' (an orphan stage
                // here). Hide it in pipeline mode.
                if !pipelineMode {
                    Button(action: onToggle) {
                        Image(systemName: task.status == "completed" ? "checkmark.circle.fill" : "circle")
                            .font(.espresso(size: 12))
                            .foregroundColor(task.status == "completed" ? .matcha500 : .secondary.opacity(0.55))
                    }
                    .buttonStyle(.plain)
                }

                Text(task.title)
                    .font(.espresso(size: 13))
                    .foregroundColor(appState.themeText)
                    .strikethrough(task.status == "completed")
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 10)
            .padding(.top, 10)
            .padding(.bottom, 6)

            VStack(alignment: .leading, spacing: 7) {
                cardAttentionContext
                cardCategoryLine
                cardMetaLine
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10)
            .padding(.bottom, 9)
        }
        // Priority edge — the card's one loud element. A 3pt capsule down the
        // left edge, colored by priority; low/none stays clean (absence is the
        // signal). Replaces the old 5pt dot nobody could see at board glance.
        .overlay(alignment: .leading) {
            if priorityEdgeVisible {
                Capsule()
                    .fill(priorityColor)
                    .frame(width: 2)
                    .padding(.vertical, 7)
                    .padding(.leading, 1.5)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .elevatedCard(cornerRadius: 8)
        // Hover lift — a whisper, not a bounce. Signals draggable/clickable.
        .scaleEffect(hovering ? 1.006 : 1.0)
        .animation(.easeOut(duration: 0.12), value: hovering)
        .onHover { hovering = $0 }
        .onTapGesture(perform: onTap)
    }

    @ViewBuilder
    private var cardAttentionContext: some View {
        if let details = autoPRRuntimeDetails {
            VStack(alignment: .leading, spacing: 4) {
                Label("AutoPR needs 10 more minutes", systemImage: "timer")
                    .font(.espresso(size: 10)).foregroundColor(.orange)
                Text(details)
                    .font(.espresso(size: 10))
                    .foregroundColor(appState.themeText.opacity(0.72))
                    .lineLimit(3)
                if task.autoprReconsiderationPending == true {
                    Label("Continuation queued", systemImage: "clock.arrow.circlepath")
                        .font(.espresso(size: 10)).foregroundStyle(.secondary)
                } else {
                    Button(action: onApproveAutoPRRuntime) {
                        Label(autoPRRuntimeApprovalInFlight ? "Approving…" : "Approve 10 more minutes",
                              systemImage: "play.circle.fill")
                            .font(.espresso(size: 10)).foregroundColor(.orange)
                    }
                    .buttonStyle(.plain)
                    .disabled(autoPRRuntimeApprovalInFlight)
                }
            }
        } else if let questions = autoPRQuestionPreview {
            VStack(alignment: .leading, spacing: 3) {
                Label("AutoPR needs an answer", systemImage: "questionmark.circle")
                    .font(.espresso(size: 10)).foregroundColor(.orange)
                Text(questions)
                    .font(.espresso(size: 10))
                    .foregroundColor(appState.themeText.opacity(0.72))
                    .lineLimit(2)
            }
        } else if let note = task.progressNote?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !note.isEmpty {
            Label {
                Text(note).lineLimit(1)
            } icon: {
                Image(systemName: "location.north.line")
            }
            .font(.espresso(size: 10))
            .foregroundColor(appState.themeText.opacity(0.58))
        }

        if task.boardColumn == "changes_requested",
           let note = task.reviewNote?.trimmingCharacters(in: .whitespacesAndNewlines),
           !note.isEmpty {
            Label {
                Text(note).lineLimit(2)
            } icon: {
                Image(systemName: "arrow.uturn.backward")
            }
            .font(.espresso(size: 10))
            .foregroundColor(.orange.opacity(0.88))
        }

        if pipelineMode, let contact = contactDisplay {
            Label(contact, systemImage: "building.2")
                .font(.espresso(size: 10))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }

    @ViewBuilder
    private var cardCategoryLine: some View {
        if KanbanTemplate.from(category: task.category) != nil
            || (elementName ?? task.elementName) != nil {
            HStack(spacing: 8) {
                if let template = KanbanTemplate.from(category: task.category) {
                    Label(template.displayName, systemImage: template.icon)
                        .foregroundColor(template.color)
                        .lineLimit(1)
                }
                if let name = elementName ?? task.elementName {
                    Label(name, systemImage: "square.stack.3d.up")
                        .foregroundColor(appState.themeAccent)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .font(.espresso(size: 10))
        }
    }

    private var cardMetaLine: some View {
        HStack(spacing: 7) {
            if let cycles = task.reviewCycleCount, cycles > 0 {
                Label("×\(cycles)", systemImage: "arrow.triangle.2.circlepath")
                    .foregroundColor(.orange)
                    .help("Sent back from review \(cycles) time\(cycles == 1 ? "" : "s")")
            }

            let unviewed = TicketUpdatesStore.shared.unviewedCount(task)
            if unviewed > 0 {
                Label("\(unviewed)", systemImage: "bell.fill")
                    .foregroundColor(.blue)
                    .help("\(unviewed) unviewed update\(unviewed == 1 ? "" : "s")")
            }

            if !pipelineMode, pendingCommitCount > 0 {
                Label("\(pendingCommitCount)", systemImage: "sparkles")
                    .foregroundColor(.purple)
                    .help("\(pendingCommitCount) possible commit completion\(pendingCommitCount == 1 ? "" : "s")")
            }

            if pipelineMode, let value = task.dealValue, value > 0 {
                Text(formatDealValue(value)).foregroundColor(appState.themeAccent)
            }

            if pipelineMode, task.dealOutcome != "open" {
                Text(task.dealOutcome.capitalized)
                    .foregroundColor(task.dealOutcome == "won" ? .green : .red)
            }

            if let name = assigneeDisplay {
                ChannelAvatarView(
                    senderId: task.assignedTo ?? task.id,
                    payloadURL: task.assignedAvatarUrl,
                    name: name,
                    size: 14
                )
                Text(name)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }

            if let total = task.subtaskTotal, total > 0 {
                let done = task.subtaskDone ?? 0
                Label("\(done)/\(total)", systemImage: done >= total ? "checkmark.circle.fill" : "checklist")
                    .foregroundColor(done >= total ? .matcha500 : .secondary)
                    .help("\(done) of \(total) checklist items complete")
            }

            if !attachments.isEmpty {
                Label("\(attachments.count)", systemImage: "paperclip")
                    .foregroundStyle(.secondary)
            }

            if let due = task.dueDate, !due.isEmpty {
                Label(String(due.prefix(10)), systemImage: "calendar")
                    .foregroundStyle(.secondary)
                    .help("Due \(due.prefix(10))")
            }

            Spacer(minLength: 0)
            timestampLine
            moveMenu
        }
        .font(.espresso(size: 10))
    }

    private var moveMenu: some View {
        Menu {
            ForEach(columnsFor(pipeline: pipelineMode), id: \.key) { column in
                Button {
                    if column.key != task.boardColumn { onMoveColumn(column.key) }
                } label: {
                    if column.key == task.boardColumn {
                        Label(column.label, systemImage: "checkmark")
                    } else {
                        Text(column.label)
                    }
                }
            }
        } label: {
            Image(systemName: "ellipsis")
                .font(.espresso(size: 11))
                .foregroundStyle(.secondary)
                .frame(width: 16, height: 16)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Move from \(currentColumnLabel)")
        .accessibilityLabel("Move card")
    }

    /// Only critical/high get the edge — medium is the default priority, so
    /// marking it would put an accent on nearly every card and the signal
    /// would drown. Absence = normal.
    private var priorityEdgeVisible: Bool {
        task.priority == "critical" || task.priority == "high"
    }

    /// Inactivity-age accent for the footer clock/time. Nil when fresh/done.
    private var agingColor: Color? {
        switch task.aging {
        case .none: return nil
        case .warn: return .orange
        case .overdue: return .red
        }
    }

    /// Compact activity date in Pacific time; the full
    /// "Added <date> at <time>" detail lives in the tooltip so the card face
    /// stays quiet. Once a card has moved, its last move replaces the added
    /// date rather than adding a second timestamp to an already dense footer.
    @ViewBuilder
    private var timestampLine: some View {
        if let added = PacificDateFormatter.shortDate(task.createdAt) {
            Group {
                if let moved = PacificDateFormatter.relative(task.lastMovedAt) {
                    Text(moved)
                } else {
                    Text(added)
                }
            }
            .font(.espresso(size: 9))
            .foregroundColor(agingColor?.opacity(0.9) ?? .secondary.opacity(0.8))
            .help("Added \(PacificDateFormatter.dateTime(task.createdAt) ?? added)")
        }
    }
}
