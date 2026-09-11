import SwiftUI

/// Review an AI-drafted reply before it leaves the mailbox. The server has
/// already saved it as a Gmail draft in the thread: "Keep as Gmail draft"
/// just closes; "Send now" sends this edited text (threaded) and removes the
/// now-redundant saved draft.
struct EmailReplySheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    let draft: EmailDraftResponse
    let original: EmailMessage?
    var onSent: () -> Void = {}

    @State private var to: String
    @State private var subject: String
    @State private var text: String
    @State private var sending = false
    @State private var error: String?

    init(draft: EmailDraftResponse, original: EmailMessage?, onSent: @escaping () -> Void = {}) {
        self.draft = draft
        self.original = original
        self.onSent = onSent
        _to = State(initialValue: draft.to)
        // Already the reply subject saved on the Gmail draft (the server owns
        // the Re: rule).
        _subject = State(initialValue: draft.subject)
        _text = State(initialValue: draft.body)
    }

    private func isBlank(_ value: String) -> Bool {
        value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var canSend: Bool {
        !sending && !isBlank(to) && !isBlank(subject) && !isBlank(text)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeAccent)
                Text("AI reply draft")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
            }
            Text("Saved to your Gmail drafts. Edit it here and send, or keep it as a draft.")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)

            field("To", text: $to)
            field("Subject", text: $subject)

            TextEditor(text: $text)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .scrollContentBackground(.hidden)
                .padding(6)
                .frame(minHeight: 220)
                .background(appState.themeCard)
                .cornerRadius(6)

            if let error {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9))
                    Text(error).font(.system(size: 11))
                }
                .foregroundColor(.orange)
            }

            HStack {
                Button("Keep as Gmail draft") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button {
                    Task { await send() }
                } label: {
                    if sending {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Send now")
                    }
                }
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(!canSend)
                .help("⌘↩ to send from your Gmail")
            }
        }
        .padding(16)
        .frame(width: 480)
        .background(Color.appBackground)
    }

    private func field(_ label: String, text: Binding<String>) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 52, alignment: .leading)
            TextField(label, text: text)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 12))
        }
    }

    private func send() async {
        guard canSend else { return }
        sending = true
        error = nil
        defer { sending = false }
        do {
            try await EmailService.shared.send(
                to: to.trimmingCharacters(in: .whitespacesAndNewlines),
                subject: subject.trimmingCharacters(in: .whitespacesAndNewlines),
                body: text,
                threadId: draft.threadId ?? original?.threadId,
                inReplyTo: draft.inReplyTo ?? original?.messageIdHeader,
                draftId: draft.draftId
            )
            onSent()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// Turn emails into an `email` kanban card: pick a collab board, fill the
/// template, optionally hand it to AutoPR (only offered on a board that is
/// watched, granted `email`, and has the bot as a collaborator). The server
/// then attaches each message as an `email-<id8>.md` snapshot — the corpus the
/// AutoPR run reads, since the sandbox never touches Gmail.
struct EmailSendToBoardSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    let emails: [EmailMessage]
    var onCreated: (_ boardTitle: String) -> Void = { _ in }

    @AppStorage("email.sendToBoard.lastProjectId") private var lastProjectId = ""

    @State private var boards: [MWProject] = []
    @State private var loadingBoards = true
    @State private var projectId: String?
    @State private var caps: MatchaWorkService.AutoPRBoardCapabilities?
    @State private var botIsCollaborator = false
    @State private var checkingAutoPR = false
    @State private var title: String
    @State private var values: [String: String] = ["tone": "professional"]
    @State private var assignToBot = false
    @State private var creating = false
    @State private var error: String?
    /// Set once the card exists, so a retry after a failed attach only
    /// re-attaches instead of creating a second card.
    @State private var createdTaskId: String?

    private let template = KanbanTemplate.email

    init(emails: [EmailMessage], onCreated: @escaping (_ boardTitle: String) -> Void = { _ in }) {
        self.emails = emails
        self.onCreated = onCreated
        let subject = emails.first?.subject.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var base = subject.isEmpty ? "Email" : "Email: \(subject)"
        if emails.count > 1 { base += " (+\(emails.count - 1))" }
        _title = State(initialValue: String(base.prefix(120)))
    }

    private var fields: [KanbanTemplate.TicketField] { template.fields }

    private var canAssignBot: Bool {
        guard let pid = projectId, let caps else { return false }
        return caps.isWatched(pid)
            && caps.has("email", on: pid)
            && caps.autoprBotUserId != nil
            && botIsCollaborator
    }

    private var autoPRHint: String? {
        guard let pid = projectId else { return nil }
        if checkingAutoPR { return "Checking whether AutoPR can run this card…" }
        guard let caps else { return nil }
        if !caps.isWatched(pid) {
            return "AutoPR doesn't watch this board, so the card is yours to work by hand."
        }
        if !caps.has("email", on: pid) {
            return "This board isn't granted email (Admin → Settings → AutoPR board capabilities), so AutoPR can't run it."
        }
        if caps.autoprBotUserId == nil || !botIsCollaborator {
            return "AutoPR isn't a collaborator on this board, so it can't pick the card up."
        }
        return assignToBot
            ? "AutoPR runs it on the next pass and attaches a triage report. Reply drafts wait for you to approve each one."
            : nil
    }

    private var canCreate: Bool {
        !creating && projectId != nil && !emails.isEmpty
            && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "rectangle.stack.badge.plus")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeAccent)
                Text("Send to board")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
            }
            Text(emails.count == 1
                 ? "Creates an Email card with this message attached as a snapshot."
                 : "Creates an Email card with these \(emails.count) messages attached as snapshots.")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)

            boardPicker
            labeled("Title") {
                TextField("Card title", text: $title)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 12))
                    .disabled(createdTaskId != nil)
            }
            ForEach(fields) { field in fieldEditor(field) }

            Toggle("Assign to AutoPR", isOn: $assignToBot)
                .toggleStyle(.checkbox)
                .font(.system(size: 12))
                .disabled(!canAssignBot || createdTaskId != nil)
            if let autoPRHint {
                Text(autoPRHint)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let error {
                HStack(alignment: .top, spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9))
                    Text(error).font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
                }
                .foregroundColor(.orange)
            }

            HStack {
                Button(createdTaskId == nil ? "Cancel" : "Close") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button {
                    Task { await create() }
                } label: {
                    if creating {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(createdTaskId == nil ? "Create card" : "Retry attaching")
                    }
                }
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(!canCreate)
            }
        }
        .padding(16)
        .frame(width: 480)
        .background(Color.appBackground)
        .task { await loadBoards() }
        .onChange(of: projectId) { _, pid in
            Task { await loadAutoPR(for: pid) }
        }
    }

    @ViewBuilder
    private var boardPicker: some View {
        labeled("Board") {
            if loadingBoards {
                ProgressView().controlSize(.small)
            } else if boards.isEmpty {
                Text("No collab boards yet — create one under Projects first.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                Picker("Board", selection: $projectId) {
                    ForEach(boards) { board in
                        Text(board.title).tag(Optional(board.id))
                    }
                }
                .labelsHidden()
                .disabled(createdTaskId != nil)
            }
        }
    }

    private func labeled<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeTextSecondary)
            content()
        }
    }

    private func binding(_ key: String) -> Binding<String> {
        Binding(get: { values[key] ?? "" }, set: { values[key] = $0 })
    }

    @ViewBuilder
    private func fieldEditor(_ field: KanbanTemplate.TicketField) -> some View {
        labeled(field.label) {
            switch field.kind {
            case .singleLine:
                TextField(field.placeholder, text: binding(field.key))
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 12))
            case .multiLine:
                TextEditor(text: binding(field.key))
                    .font(.system(size: 12))
                    .scrollContentBackground(.hidden)
                    .padding(4)
                    .frame(height: 70)
                    .background(appState.themeCard)
                    .cornerRadius(6)
            case .picker(let options):
                Picker(field.label, selection: binding(field.key)) {
                    ForEach(options, id: \.self) { option in
                        Text(option.capitalized).tag(option)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
            }
        }
        .disabled(createdTaskId != nil)
    }

    // MARK: loading

    /// Kanban boards live on collab projects.
    private func loadBoards() async {
        loadingBoards = true
        defer { loadingBoards = false }
        do {
            let all = try await MatchaWorkService.shared.listProjects()
            boards = all
                .filter { $0.projectType == "collab" && $0.status != "archived" }
                .sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
            if projectId == nil {
                projectId = boards.first(where: { $0.id == lastProjectId })?.id ?? boards.first?.id
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func loadAutoPR(for pid: String?) async {
        caps = nil
        botIsCollaborator = false
        assignToBot = false
        guard let pid else { return }
        checkingAutoPR = true
        let fetched = try? await MatchaWorkService.shared.autoprBoardCapabilities(projectId: pid)
        var isCollaborator = false
        if let bot = fetched?.autoprBotUserId, fetched?.isWatched(pid) == true,
           let collaborators = try? await MatchaWorkService.shared.listCollaborators(projectId: pid) {
            isCollaborator = collaborators.contains { $0.userId == bot }
        }
        // The user may have switched boards while this was in flight; the
        // newer load owns the state then.
        guard projectId == pid else { return }
        caps = fetched
        botIsCollaborator = isCollaborator
        checkingAutoPR = false
        assignToBot = canAssignBot
    }

    // MARK: create

    private func create() async {
        guard let pid = projectId, canCreate else { return }
        creating = true
        error = nil
        defer { creating = false }
        let boardTitle = boards.first(where: { $0.id == pid })?.title ?? "the board"
        do {
            let taskId: String
            if let createdTaskId {
                taskId = createdTaskId
            } else {
                let description = KanbanTemplate.composeDescription(fields: fields, values: values)
                let task = try await MatchaWorkService.shared.createProjectTask(
                    projectId: pid,
                    title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                    boardColumn: "todo",
                    description: description.isEmpty ? nil : description,
                    priority: template.defaultPriority,
                    assignedTo: (assignToBot && canAssignBot) ? caps?.autoprBotUserId : nil,
                    category: template.rawValue
                )
                taskId = task.id
                createdTaskId = task.id
            }
            let result = try await EmailService.shared.snapshot(
                emailIds: emails.map(\.id), projectId: pid, taskId: taskId
            )
            MatchaWorkService.shared.invalidateProjectTasks(projectId: pid)
            let failed = result.skipped.filter { $0.reason == "fetch_failed" }.count
            if failed > 0 {
                error = failed == emails.count
                    ? "The card is on \(boardTitle), but the email couldn't be read from Gmail. Retry to attach it."
                    : "The card is on \(boardTitle), but \(failed) of \(emails.count) emails couldn't be read from Gmail. Retry to attach them."
                return
            }
            lastProjectId = pid
            onCreated(boardTitle)
            dismiss()
        } catch {
            self.error = createdTaskId == nil
                ? error.localizedDescription
                : "The card is on \(boardTitle), but attaching the email failed: \(error.localizedDescription)"
        }
    }
}
