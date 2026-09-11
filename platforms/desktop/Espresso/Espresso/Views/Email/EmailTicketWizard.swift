import SwiftUI

/// Guided setup for an `email` kanban ticket: pick the messages, say what the
/// agent should do with them, pick a reply tone, then review exactly what
/// AutoPR will and won't do. Local-only — nothing is created or attached until
/// the ticket form is submitted, which then snapshots the picked emails onto
/// the new card.
struct EmailTicketWizard: View {
    struct Brief {
        let title: String
        let values: [String: String]
        let emails: [EmailMessage]
    }

    enum Goal: String, CaseIterable, Identifiable {
        case triage, summarize, actions, custom

        var id: String { rawValue }

        var label: String {
            switch self {
            case .triage: return "Triage & draft replies"
            case .summarize: return "Summarize"
            case .actions: return "Pull out action items"
            case .custom: return "Something else"
            }
        }

        var icon: String {
            switch self {
            case .triage: return "arrowshape.turn.up.left.2"
            case .summarize: return "text.alignleft"
            case .actions: return "checklist"
            case .custom: return "pencil"
            }
        }

        var blurb: String {
            switch self {
            case .triage: return "Sort each email, summarize it, and draft replies where someone is waiting."
            case .summarize: return "A short summary of each email and what it asks of you."
            case .actions: return "Every task, deadline and amount, as a checklist."
            case .custom: return "Describe the job yourself below."
            }
        }

        /// What lands in the ticket's goal field.
        var text: String {
            switch self {
            case .triage: return "Sort these emails, summarize each one, and draft replies to the ones that need an answer."
            case .summarize: return "Summarize these emails and flag anything I need to act on."
            case .actions: return "List every action item, deadline, and amount in these emails as a checklist."
            case .custom: return ""
            }
        }

        /// Opens the suggested ticket title.
        var titlePrefix: String {
            switch self {
            case .triage: return "Reply to"
            case .summarize: return "Summarize"
            case .actions: return "Action items"
            case .custom: return "Email"
            }
        }
    }

    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    private let vm = EmailViewModel.shared
    let onApply: (Brief) -> Void

    /// The server's per-card snapshot cap (from `/status`).
    private var maxEmails: Int { vm.snapshotLimit }
    private static let steps = ["Emails", "Goal", "Replies", "Review"]
    private static let tones = ["professional", "casual", "brief"]

    @State private var step = 0
    @State private var picked: [String]
    /// Messages already chosen on an earlier pass may have left the unread
    /// list since; keep them so reopening the wizard doesn't drop them.
    @State private var known: [String: EmailMessage]
    @State private var search = ""
    @State private var goal: Goal
    @State private var goalText: String
    @State private var instructions: String
    @State private var tone: String
    @State private var title: String

    init(
        initialTitle: String = "",
        initialValues: [String: String] = [:],
        initialEmails: [EmailMessage] = [],
        onApply: @escaping (Brief) -> Void
    ) {
        self.onApply = onApply
        let existingGoal = (initialValues["goal"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let preset = Goal.allCases.first { $0 != .custom && $0.text == existingGoal }
        _goal = State(initialValue: existingGoal.isEmpty ? .triage : (preset ?? .custom))
        _goalText = State(initialValue: existingGoal.isEmpty ? Goal.triage.text : existingGoal)
        _instructions = State(initialValue: initialValues["instructions"] ?? "")
        let existingTone = initialValues["tone"] ?? ""
        _tone = State(initialValue: Self.tones.contains(existingTone) ? existingTone : "professional")
        _picked = State(initialValue: initialEmails.map(\.id))
        _known = State(initialValue: Dictionary(initialEmails.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }))
        _title = State(initialValue: initialTitle)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("Email ticket", systemImage: "envelope")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Text("Step \(step + 1) of \(Self.steps.count) · \(Self.steps[step])")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
            ProgressView(value: Double(step + 1), total: Double(Self.steps.count))
                .tint(appState.themeAccent)
            Text(heading)
                .font(.system(size: 22, weight: .semibold))

            Group {
                switch step {
                case 0: emailsStep
                case 1: goalStep
                case 2: toneStep
                default: reviewStep
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            Divider()
            HStack {
                Button("Cancel") { dismiss() }
                Spacer()
                if step > 0 {
                    Button("Back") { step -= 1 }
                }
                Button(step == Self.steps.count - 1 ? "Use this brief" : "Continue") { advance() }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canContinue)
            }
        }
        .padding(28)
        .frame(width: 660, height: 640)
        .background(Color.appBackground)
        .task {
            if !vm.statusLoaded {
                await vm.loadStatus()
            } else if vm.connected {
                await vm.refreshIfStale()
            }
        }
        .onChange(of: goalText) { _, text in
            if goal != .custom && text != goal.text { goal = .custom }
        }
    }

    // MARK: - Flow

    private var heading: String {
        switch step {
        case 0: return "Which emails should the agent work on?"
        case 1: return "What should it do with them?"
        case 2: return "How should replies sound?"
        default: return "Review the ticket"
        }
    }

    private var pickedEmails: [EmailMessage] {
        picked.compactMap { known[$0] ?? vm.message(id: $0) }
    }

    private var canContinue: Bool {
        switch step {
        case 0: return !pickedEmails.isEmpty && picked.count <= maxEmails
        case 1: return !goalText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case 2: return true
        default: return !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !pickedEmails.isEmpty
        }
    }

    private var suggestedTitle: String {
        let emails = pickedEmails
        let subject = emails.first?.subject.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var result = "\(goal.titlePrefix): \(subject.isEmpty ? "email" : subject)"
        if emails.count > 1 { result += " (+\(emails.count - 1))" }
        return String(result.prefix(120))
    }

    private func advance() {
        guard canContinue else { return }
        if step < Self.steps.count - 1 {
            step += 1
            if step == Self.steps.count - 1,
               title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                title = suggestedTitle
            }
            return
        }
        onApply(Brief(
            title: title.trimmingCharacters(in: .whitespacesAndNewlines),
            values: [
                "goal": goalText.trimmingCharacters(in: .whitespacesAndNewlines),
                "instructions": instructions.trimmingCharacters(in: .whitespacesAndNewlines),
                "tone": tone,
            ],
            emails: pickedEmails
        ))
        dismiss()
    }

    private func toggle(_ msg: EmailMessage) {
        if let index = picked.firstIndex(of: msg.id) {
            picked.remove(at: index)
        } else if picked.count < maxEmails {
            picked.append(msg.id)
            known[msg.id] = msg
        }
    }

    // MARK: - Step 1: emails

    /// Unread mail, plus anything picked earlier that has since left it.
    private var candidates: [EmailMessage] {
        let listed = Set(vm.emails.map(\.id))
        let carried = picked.compactMap { known[$0] }.filter { !listed.contains($0.id) }
        let all = carried + vm.emails
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return all }
        return all.filter {
            $0.subject.lowercased().contains(q)
                || $0.fromAddress.lowercased().contains(q)
                || ($0.snippet ?? "").lowercased().contains(q)
        }
    }

    private var needsReplyIds: [String] {
        vm.emails.filter { vm.bucket(of: $0.id) == .needsReply }.map(\.id)
    }

    @ViewBuilder
    private var emailsStep: some View {
        if !vm.statusLoaded {
            ProgressView()
                .controlSize(.small)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if !vm.connected {
            VStack(alignment: .leading, spacing: 12) {
                Text("Connect Gmail first. The emails you pick are copied onto the ticket as read-only snapshots, so the agent never gets access to your mailbox.")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button {
                    Task { await vm.connect() }
                } label: {
                    Text(vm.isConnecting ? "Waiting for Google…" : "Connect Gmail")
                }
                .buttonStyle(.borderedProminent)
                .disabled(vm.isConnecting)
                if let err = vm.errorMessage {
                    Text(err).font(.system(size: 11)).foregroundColor(.orange)
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("Pick up to \(maxEmails) from your unread mail. Each one is attached to the ticket as a read-only snapshot, and the agent reads only those.")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 8) {
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        TextField("Search mail", text: $search)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                    }
                    .padding(.horizontal, 8).padding(.vertical, 6)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(6)
                    let replyIds = needsReplyIds
                    if !replyIds.isEmpty {
                        Button("Pick the \(replyIds.count) that need a reply") {
                            for id in replyIds where !picked.contains(id) && picked.count < maxEmails {
                                picked.append(id)
                                if let msg = vm.message(id: id) { known[id] = msg }
                            }
                        }
                        .buttonStyle(.borderless)
                        .font(.system(size: 11, weight: .medium))
                    }
                }
                if vm.isLoading && vm.emails.isEmpty {
                    ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if candidates.isEmpty {
                    Text(search.isEmpty ? "No unread mail to attach." : "No matches.")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 2) {
                            ForEach(candidates) { msg in pickRow(msg) }
                        }
                        .padding(4)
                    }
                    .background(appState.themeText.opacity(0.03))
                    .cornerRadius(8)
                }
                HStack {
                    Text("\(picked.count) of \(maxEmails) picked")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                    Spacer()
                    if !picked.isEmpty {
                        Button("Clear") { picked = [] }
                            .buttonStyle(.borderless)
                            .font(.system(size: 11))
                    }
                }
            }
        }
    }

    private func pickRow(_ msg: EmailMessage) -> some View {
        let isPicked = picked.contains(msg.id)
        let atCap = !isPicked && picked.count >= maxEmails
        let info = vm.rowInfo(for: msg)
        return Button { toggle(msg) } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: isPicked ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 15))
                    .foregroundColor(isPicked ? appState.themeAccent : .secondary)
                EmailAvatar(initial: info.initial, tint: info.tint, size: 24)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(info.senderName)
                            .font(.system(size: 12, weight: .semibold))
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        if let bucket = vm.bucket(of: msg.id) {
                            EmailBucketChip(bucket: bucket)
                        }
                        Text(info.dateLabel)
                            .font(.system(size: 10.5))
                            .foregroundColor(.secondary)
                    }
                    Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                        .font(.system(size: 12))
                        .lineLimit(1)
                    if !info.preview.isEmpty {
                        Text(info.preview)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 7).fill(isPicked ? appState.themeAccent.opacity(0.10) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundColor(appState.themeText)
        .disabled(atCap)
        .opacity(atCap ? 0.5 : 1)
    }

    // MARK: - Step 2: goal

    private var goalStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                ForEach(Goal.allCases) { option in goalCard(option) }
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("The ask, in your words")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.secondary)
                TextField("e.g. Find the invoices and tell me which are overdue", text: $goalText, axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .lineLimit(2...4)
                    .padding(10)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(8)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Anything it should know? (optional)")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.secondary)
                TextField(
                    "e.g. Only draft replies to customers. Offer Friday 10am for any meeting request. Ignore vendor newsletters.",
                    text: $instructions,
                    axis: .vertical
                )
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .lineLimit(3...6)
                .padding(10)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(8)
            }
        }
    }

    private func goalCard(_ option: Goal) -> some View {
        let selected = goal == option
        return Button {
            goal = option
            if option != .custom {
                goalText = option.text
            } else if Goal.allCases.contains(where: { $0 != .custom && $0.text == goalText }) {
                goalText = ""
            }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Image(systemName: option.icon)
                        .foregroundColor(selected ? appState.themeAccent : .secondary)
                    Text(option.label)
                        .font(.system(size: 13, weight: .semibold))
                }
                Text(option.blurb)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 66, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 9)
                    .fill(selected ? appState.themeAccent.opacity(0.10) : appState.themeText.opacity(0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9)
                    .stroke(selected ? appState.themeAccent.opacity(0.6) : Color.clear, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundColor(appState.themeText)
    }

    // MARK: - Step 3: tone

    private var toneStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            Picker("Tone", selection: $tone) {
                Text("Professional").tag("professional")
                Text("Casual").tag("casual")
                Text("Brief").tag("brief")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 360)
            VStack(alignment: .leading, spacing: 6) {
                Text("EXAMPLE")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary)
                Text(toneExample)
                    .font(.system(size: 13))
                    .lineSpacing(3)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(appState.themeAccent.opacity(0.07))
            .cornerRadius(10)
            Label("Replies are drafts. Nothing is sent until you approve each one on the ticket.", systemImage: "hand.raised")
                .font(.system(size: 12))
                .foregroundColor(.secondary)
        }
    }

    private var toneExample: String {
        switch tone {
        case "casual": return "Hey Alice — Friday works great for me. Talk then!"
        case "brief": return "Friday 10am works. Thanks."
        default: return "Hi Alice, thanks for the note. Friday at 10am works well for me; I'll send an invite shortly. Best,"
        }
    }

    // MARK: - Step 4: review

    private var reviewStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Ticket title")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.secondary)
                    TextField("Ticket title", text: $title)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14, weight: .semibold))
                        .padding(9)
                        .background(appState.themeText.opacity(0.06))
                        .cornerRadius(7)
                }
                reviewBlock("Emails (\(pickedEmails.count))") {
                    ForEach(pickedEmails) { msg in
                        HStack(spacing: 6) {
                            Text(vm.rowInfo(for: msg).senderName).fontWeight(.semibold)
                            Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                                .foregroundColor(.secondary)
                        }
                        .font(.system(size: 12))
                        .lineLimit(1)
                    }
                }
                reviewBlock("Goal") {
                    Text(goalText).font(.system(size: 13))
                }
                if !instructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    reviewBlock("Instructions") {
                        Text(instructions).font(.system(size: 13))
                    }
                }
                reviewBlock("Reply tone") {
                    Text(tone.capitalized).font(.system(size: 13))
                }
                whatHappensNext
                Text("Next, pick the priority and assignee on the ticket form.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func reviewBlock<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.secondary)
            content()
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(appState.themeText.opacity(0.04))
        .cornerRadius(8)
    }

    private var whatHappensNext: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("What happens next")
                .font(.system(size: 12, weight: .semibold))
            bullet("paperclip", "Creating the ticket attaches each email as a read-only snapshot. The agent never touches your mailbox.")
            bullet("cpu", "Assigned to AutoPR on a board granted email access, it reads only those snapshots, attaches a triage report, and moves the card to Review.")
            bullet("hand.raised", "Reply drafts wait on the card as proposed actions. Each needs your approval, and sending needs the board's outreach grant.")
            bullet("person", "Not assigned to AutoPR? The ticket is yours to work by hand, with the emails attached for context.")
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(appState.themeAccent.opacity(0.07))
        .cornerRadius(10)
    }

    private func bullet(_ icon: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundColor(appState.themeAccent)
                .frame(width: 16)
            Text(text)
                .font(.system(size: 12))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
