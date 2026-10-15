import SwiftUI
import AppKit
import UniformTypeIdentifiers

// Espresso Tasks in the conversation: the card a task posts where it started
// (and again when it ends), and the form Espresso asks for a task's details.

extension AgentCardMessageView {
    /// "On it" when a task starts; the headline and top findings when it ends.
    func taskCard(_ task: AgentTaskCard) -> some View {
        card {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: TaskChatText.icon(task))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(task.status == "failed" ? .orange : appState.themeAccent)
                    Text(TaskChatText.lead(task))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                    Spacer(minLength: 0)
                }
                Text(task.title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                if let line = TaskChatText.body(task) {
                    Text(line)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(task.items) { item in
                    Button { appState.openTasks(taskId: task.taskId, itemId: item.id) } label: {
                        HStack(alignment: .top, spacing: 8) {
                            if item.image != nil { photo(item.image, size: 40) }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.title).font(.system(size: 12, weight: .semibold)).lineLimit(1)
                                if !item.subtitle.isEmpty {
                                    Text(item.subtitle).font(.system(size: 11))
                                        .foregroundColor(appState.themeTextSecondary).lineLimit(1)
                                }
                                let facts = item.fields.values.sorted().prefix(4).joined(separator: " \u{00B7} ")
                                if !facts.isEmpty {
                                    Text(facts).font(.system(size: 10))
                                        .foregroundColor(appState.themeTextSecondary).lineLimit(1)
                                }
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right").font(.system(size: 9))
                                .foregroundColor(appState.themeTextSecondary)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(appState.themeText)
                }
                Button {
                    appState.openTasks(taskId: task.taskId)
                } label: {
                    Label("Open in Tasks", systemImage: "list.bullet.clipboard").font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.link)
            }
        }
    }

    /// The form a task's details are asked with. Its owner fills and submits
    /// it (the task starts with no model run); anyone can still just reply.
    func formCard(_ view: AgentChatPromptView, _ form: IntakeForm) -> some View {
        card {
            IntakeFormCard(
                question: view.question ?? text,
                form: form,
                promptId: meta.promptId,
                status: (meta.promptStatus ?? "open"),
                closedText: meta.answerText,
                mine: meta.ownerUserId.map { $0 == currentUserId } ?? true,
                channelId: channelId
            )
        }
    }
}

/// Words for a task card, kept apart so they can be tested.
enum TaskChatText {
    static func lead(_ task: AgentTaskCard) -> String {
        if task.event == "started" { return "Started a task" }
        switch task.status {
        case "done": return "Task done"
        case "failed": return "Task stopped"
        case "waiting": return "Task needs you"
        default: return "Task"
        }
    }

    static func icon(_ task: AgentTaskCard) -> String {
        if task.event == "started" { return "play.circle" }
        switch task.status {
        case "done": return "checkmark.circle.fill"
        case "failed": return "exclamationmark.triangle.fill"
        case "waiting": return "hand.raised.fill"
        default: return "list.bullet.clipboard"
        }
    }

    static func body(_ task: AgentTaskCard) -> String? {
        if task.event == "started" { return "It runs in the background. I'll post here when it's done." }
        let line = task.headline ?? task.note
        return line.isEmpty ? nil : line
    }
}

/// Fill in a task's details and start it.
struct IntakeFormCard: View {
    @Environment(AppState.self) private var appState
    let question: String
    let form: IntakeForm
    let promptId: String?
    /// open / answered / superseded / expired (`agent_card_prompt_updated`).
    let status: String
    let closedText: String?
    let mine: Bool
    let channelId: String?

    @State private var text: [String: String] = [:]
    @State private var files: [String: [PendingChannelAttachment]] = [:]
    @State private var agreed = false
    @State private var sending = false
    @State private var problems: [String] = []
    @State private var startedTaskId: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(question)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(appState.themeText)
            Text(form.units > 0 ? "\(form.label) \u{00B7} uses \(form.units) units when it starts" : form.label)
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
            if !form.known.isEmpty {
                TaskChips(items: form.known.map { "\($0.label): \($0.shown)" })
            }
            if let started = startedTaskId {
                startedRow(started)
            } else if status != "open" {
                Label(closedText ?? (status == "answered" ? "Answered" : "Closed"), systemImage: "checkmark.circle")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeTextSecondary)
            } else if !mine {
                Text("Waiting for the person it asked.").font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            } else {
                fields
                if let consent = form.consent { consentBox(consent) }
                ForEach(problems, id: \.self) { problem in
                    Text(problem).font(.system(size: 11)).foregroundColor(.orange)
                }
                HStack {
                    Text("Or just reply here.").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    Spacer()
                    if sending { ProgressView().controlSize(.small) }
                    Button(form.submitLabel) { Task { await submit() } }
                        .buttonStyle(.borderedProminent)
                        .tint(appState.themeAccent)
                        .controlSize(.small)
                        .disabled(sending || promptId == nil || (form.consent != nil && !agreed))
                }
            }
        }
        .onAppear {
            for field in form.fields where text[field.key] == nil && !field.initial.isEmpty {
                text[field.key] = field.initial
            }
        }
    }

    private var fields: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(form.fields) { field in
                VStack(alignment: .leading, spacing: 3) {
                    Text(field.label + (field.optional ? " (optional)" : field.required ? "" : ""))
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(appState.themeText)
                    input(field)
                    if !field.help.isEmpty {
                        Text(field.help).font(.system(size: 9)).foregroundColor(appState.themeTextSecondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func input(_ field: IntakeFormField) -> some View {
        if field.type == "file" {
            fileInput(field)
        } else {
            IntakeFieldInput(field: field, value: Binding(get: { text[field.key] ?? "" }, set: { text[field.key] = $0 }))
        }
    }

    private func fileInput(_ field: IntakeFormField) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(files[field.key] ?? []) { file in
                HStack(spacing: 6) {
                    Image(systemName: file.isImage ? "photo" : "doc").font(.system(size: 10))
                    Text(file.filename).font(.system(size: 11)).lineLimit(1)
                    Button { files[field.key]?.removeAll { $0.id == file.id } } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 10))
                    }
                    .buttonStyle(.plain)
                }
                .foregroundColor(appState.themeTextSecondary)
            }
            if (files[field.key] ?? []).count < field.maxCount {
                Button("Add file…") { pickFiles(for: field) }.controlSize(.small)
            }
        }
    }

    private func consentBox(_ consent: IntakeFormConsent) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(consent.title).font(.system(size: 11, weight: .semibold))
            ForEach(consent.body, id: \.self) { line in
                Text(line).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Toggle("I agree", isOn: $agreed).toggleStyle(.checkbox).font(.system(size: 11))
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8).fill(appState.themeText.opacity(0.04)))
    }

    private func startedRow(_ taskId: String) -> some View {
        HStack(spacing: 8) {
            Label("Started", systemImage: "checkmark.circle.fill")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeAccent)
            Button("Open in Tasks") { appState.openTasks(taskId: taskId) }
                .buttonStyle(.link).font(.system(size: 11))
        }
    }

    // MARK: Files

    private func pickFiles(for field: IntakeFormField) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = field.maxCount > 1
        panel.canChooseDirectories = false
        panel.allowedContentTypes = IntakeFormCard.contentTypes(field.accept)
        guard panel.runModal() == .OK else { return }
        for url in panel.urls {
            guard let data = try? Data(contentsOf: url) else { continue }
            if field.maxBytes > 0 && data.count > field.maxBytes {
                problems = ["\(url.lastPathComponent) is larger than \(field.maxBytes / 1_048_576) MB."]
                continue
            }
            let mime = UTType(filenameExtension: url.pathExtension.lowercased())?.preferredMIMEType
                ?? "application/octet-stream"
            var file = PendingChannelAttachment(data: data, filename: url.lastPathComponent, mimeType: mime)
            if let converted = ChannelDetailView.convertingHEIC(file) { file = converted }
            var list = files[field.key] ?? []
            guard list.count < field.maxCount else { break }
            list.append(file)
            files[field.key] = list
        }
    }

    // MARK: Submit

    private func submit() async {
        guard let promptId else { return }
        let built = IntakeFormValues.build(form.fields, text: text,
                                           files: files.mapValues { $0.map(\.filename) })
        problems = built.problems.map(\.message)
        guard problems.isEmpty else { return }
        sending = true
        defer { sending = false }
        do {
            var inputIds: [String] = []
            let pending = files.values.flatMap { $0 }
            if !pending.isEmpty {
                guard let channelId else { problems = ["Files can't be added here."]; return }
                let uploaded = try await ChannelsService.shared.uploadAttachments(
                    channelId: channelId,
                    files: pending.map { (data: $0.data, filename: $0.filename, mimeType: $0.mimeType) })
                inputIds = uploaded.compactMap(\.privateInputId)
            }
            let task = try await AgentTaskService.shared.answerForm(
                promptId: promptId,
                answer: IntakeFormAnswer(values: built.values, inputIds: inputIds,
                                         consentVersion: form.consent?.version))
            startedTaskId = task.id
            await appState.refreshTasksSummary()
        } catch let api as APIError {
            problems = [IntakeFormCard.message(for: api)]
        } catch {
            problems = ["Couldn't start it. Try again in a moment."]
        }
    }

    // MARK: Pure helpers (tested)

    static func placeholder(_ field: IntakeFormField) -> String {
        switch field.type {
        case "money": return "$3,500"
        case "number": return "A number"
        case "date": return "YYYY-MM-DD"
        case "time": return "19:30"
        case "list", "multi_select": return "Separate with commas"
        case "location": return "A city, neighborhood or address"
        default: return ""
        }
    }

    static func contentTypes(_ accept: [String]) -> [UTType] {
        var types: [UTType] = []
        if accept.contains("image") {
            types += [.png, .jpeg, .heic] + ["webp"].compactMap { UTType(filenameExtension: $0) }
        }
        if accept.contains("document") {
            types += [.pdf, .plainText, .commaSeparatedText, .json]
            types += ["docx", "doc", "md"].compactMap { UTType(filenameExtension: $0) }
        }
        return types.isEmpty ? [.data] : types
    }

    /// The server's own words: a field-by-field list for a form it refused.
    static func message(for error: APIError) -> String {
        if case let .httpError(_, body) = error,
           let data = body.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? [String: Any],
           let errors = detail["errors"] as? [String: String], !errors.isEmpty {
            return errors.keys.sorted().compactMap { errors[$0] }.joined(separator: " ")
        }
        return AssistantText.message(for: error, fallback: "Couldn't start it. Try again in a moment.")
    }
}

/// One typed field (not a file): a picker, a switch, or a text box with a hint.
/// Shared by intake forms and an action's own fields.
struct IntakeFieldInput: View {
    let field: IntakeFormField
    @Binding var value: String

    var body: some View {
        switch field.type {
        case "select":
            Picker("", selection: $value) {
                Text("Choose…").tag("")
                ForEach(field.options, id: \.self) { Text($0).tag($0) }
            }
            .labelsHidden()
            .frame(maxWidth: 260)
        case "boolean":
            Toggle(isOn: Binding(get: { value == "yes" }, set: { value = $0 ? "yes" : "no" })) { EmptyView() }
                .toggleStyle(.switch).controlSize(.small)
        default:
            TextField(IntakeFormCard.placeholder(field), text: $value)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 12))
                .frame(maxWidth: 320)
        }
    }
}
