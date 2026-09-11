import SwiftUI

/// Create-mode sheet for template-based tickets. Distinct from the edit-only
/// `TaskEditorSheet` (whose `task` is non-optional and whose upload UI needs an
/// existing task id). Prefills the description scaffold + default priority +
/// category, then creates on Add.
struct TaskComposeContent: View {
    @Environment(AppState.self) private var appState
    let column: String
    let template: KanbanTemplate
    @Bindable var viewModel: ProjectDetailViewModel
    let onClose: () -> Void

    @State private var title: String = ""
    @State private var showingWizard = false
    @State private var creating = false
    @State private var creationError: String?

    private var fields: [KanbanTemplate.TicketField] {
        template == .research ? ResearchBriefWizard.fields : template.fields
    }
    /// One entry per `template.fields` element, keyed by field.key. Composed
    /// into the markdown description on Add.
    @State private var fieldValues: [String: String] = [:]
    @State private var priority: String
    @State private var assignedTo: String?
    @State private var selectedElementId: String?
    @State private var isAddingElement = false
    @State private var newElementName = ""
    /// Research cards run only when assigned to the AutoPR service account.
    /// Resolved from the board-capabilities endpoint when the template is
    /// research; nil when the board is not watched or the call failed.
    @State private var autoPRBotUserId: String?
    @State private var artifactGranted: Bool?
    /// nil until the capabilities call answers; false means AutoPR does not
    /// watch this board at all, which is the one case where the card provably
    /// can never run.
    @State private var boardWatchedByAutoPR: Bool?

    init(column: String, template: KanbanTemplate, viewModel: ProjectDetailViewModel, onClose: @escaping () -> Void) {
        self.column = column
        self.template = template
        self.viewModel = viewModel
        self.onClose = onClose
        _priority = State(initialValue: template.defaultPriority)
    }

    /// Research and Email cards are AutoPR artifact kinds: they only run when
    /// the bot owns them on a board granted their capability.
    private var artifactCapability: String? { template.autoprArtifactCapability }

    /// Nothing else on the sheet says that an artifact card sits in Todo
    /// forever unless the bot owns it.
    private var researchAssignmentHint: String? {
        // Said first, and without needing the bot's identity: an unwatched
        // board never resolves one, so gating the whole hint on it left the
        // one unfixable case as the only one that explained nothing, while a
        // merely-ungranted board got told.
        if boardWatchedByAutoPR == false {
            return "AutoPR does not watch this board, so a \(template.displayName) card here will not run automatically."
        }
        guard let bot = autoPRBotUserId else { return nil }
        let botIsCollaborator = viewModel.collaborators.contains { $0.userId == bot }
        if !botIsCollaborator {
            return "AutoPR is not a collaborator on this board, so this card will not run automatically."
        }
        if artifactGranted == false {
            return "This board is not granted \(artifactCapability ?? template.rawValue) (Admin → Settings → AutoPR board capabilities); the card will wait until it is."
        }
        if assignedTo == bot {
            return "Assigned to AutoPR — runs on the next pass, or press \(template.autoprRunNowLabel) on the ticket."
        }
        return "Assign to AutoPR to have it run automatically."
    }

    /// For a Research card, learn who the bot is and preselect it: the
    /// harness only picks up cards assigned to that account.
    private func loadResearchDefaults() async {
        guard let capability = artifactCapability, let pid = viewModel.project?.id else { return }
        guard let caps = try? await MatchaWorkService.shared.autoprBoardCapabilities(projectId: pid)
        else { return }
        boardWatchedByAutoPR = caps.isWatched(pid)
        guard caps.isWatched(pid), let bot = caps.autoprBotUserId else { return }
        autoPRBotUserId = bot
        artifactGranted = caps.has(capability, on: pid)
        preselectAutoPRIfPossible()
    }

    /// `collaborators` is published and loads asynchronously, so on a cold
    /// project open this check can run before the list arrives. Missing it
    /// creates the card unassigned, and the harness only picks up cards the
    /// bot owns — the card then sits in Todo forever, which is precisely what
    /// preselecting exists to prevent. Re-run when the list changes.
    private func preselectAutoPRIfPossible() {
        guard artifactCapability != nil, assignedTo == nil, let bot = autoPRBotUserId,
              viewModel.collaborators.contains(where: { $0.userId == bot }) else { return }
        assignedTo = bot
    }

    private func fieldBinding(_ key: String) -> Binding<String> {
        Binding(get: { fieldValues[key] ?? "" }, set: { fieldValues[key] = $0 })
    }

    private let priorities: [(key: String, label: String)] = [
        ("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: template.icon)
                    .font(.system(size: 12))
                    .foregroundColor(template.color)
                Text("New \(template.displayName) Ticket")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
            }

            if template == .research {
                Button { showingWizard = true } label: {
                    Label("Guide me through this research ticket", systemImage: "wand.and.stars")
                }
                .buttonStyle(.bordered)
                Text("Build a clear research brief one step at a time, with examples.")
                    .font(.system(size: 12)).foregroundColor(.secondary)
            }

            Text("Ticket title").font(.system(size: 12, weight: .semibold))
            TextField("Give this ticket a clear, specific name", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText)
                .padding(8)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(6)

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(fields) { field in
                        fieldEditor(for: field)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(minHeight: 180, maxHeight: 340)

            HStack(spacing: 6) {
                Text("Priority")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Picker("", selection: $priority) {
                    ForEach(priorities, id: \.key) { p in
                        Text(p.label).tag(p.key)
                    }
                }
                .labelsHidden()
                .fixedSize()
                Spacer()
            }

            elementPickerRow

            if !viewModel.collaborators.isEmpty {
                HStack(spacing: 6) {
                    Text("Assignee")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Picker("", selection: $assignedTo) {
                        Text("Unassigned").tag(String?.none)
                        ForEach(viewModel.collaborators) { c in
                            Text(c.name).tag(String?.some(c.userId))
                        }
                    }
                    .labelsHidden()
                    .fixedSize()
                    Spacer()
                }
            }
            if artifactCapability != nil, let hint = researchAssignmentHint {
                Text(hint)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let creationError {
                Text(creationError).font(.system(size: 12)).foregroundColor(.red)
            }
            Divider()
            HStack {
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                Spacer()
                Button(creating ? "Creating…" : "Create ticket") {
                    let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !t.isEmpty else { return }
                    let desc = KanbanTemplate.composeDescription(
                        fields: fields, values: fieldValues
                    )
                    creating = true
                    creationError = nil
                    viewModel.errorMessage = nil
                    Task {
                        await viewModel.addTask(
                            title: t, column: column, priority: priority,
                            assignedTo: assignedTo,
                            description: desc.isEmpty ? nil : desc,
                            category: template.rawValue,
                            elementId: selectedElementId
                        )
                        creating = false
                        if let error = viewModel.errorMessage {
                            creationError = error
                        } else {
                            onClose()
                        }
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(.matcha500)
                .disabled(creating || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .disabled(creating)
        .padding(24)
        .frame(width: 620)
        .frame(maxHeight: 760)
        .sheet(isPresented: $showingWizard) {
            ResearchBriefWizard(initialTitle: title, initialValues: fieldValues) { newTitle, values, _ in
                title = newTitle
                fieldValues = values
                showingWizard = false
            }
        }
        .task {
            if template == .research { showingWizard = true }
            await loadResearchDefaults()
        }
        .onChange(of: viewModel.collaborators.count) { _, _ in preselectAutoPRIfPossible() }
        .glassPanel(cornerRadius: 0, material: .hudWindow, blending: .behindWindow,
                    tint: Color.appBackground, tintOpacity: 0.62, shadow: false)
    }

    /// Renders one structured field (labeled). Single-line → TextField,
    /// multi-line → TextEditor with a placeholder overlay (TextEditor has no
    /// native placeholder), picker → segmented dropdown with an empty "—" tag.
    @ViewBuilder
    private func fieldEditor(for field: KanbanTemplate.TicketField) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(field.label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            switch field.kind {
            case .singleLine:
                TextField(field.placeholder, text: fieldBinding(field.key))
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .padding(7)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(5)
            case .multiLine:
                ComposerTextView(text: fieldBinding(field.key), placeholder: field.placeholder,
                                 font: .systemFont(ofSize: 13), textColor: appState.themeText,
                                 minLines: 3, maxLines: 8, submitKey: .commandReturnSends)
                    .padding(10)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(8)
            case .picker(let options):
                Picker("", selection: fieldBinding(field.key)) {
                    Text("—").tag("")
                    ForEach(options, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .fixedSize()
            }
        }
    }

    /// Element row: pick an existing element or create one inline via "＋ New".
    @ViewBuilder
    private var elementPickerRow: some View {
        HStack(spacing: 6) {
            Text("Element")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            if isAddingElement {
                TextField("New element name", text: $newElementName)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .padding(6)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(5)
                    .frame(maxWidth: 180)
                    .onSubmit { commitNewElement() }
                Button("Add") { commitNewElement() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                    .disabled(newElementName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Cancel") { isAddingElement = false; newElementName = "" }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                Picker("", selection: $selectedElementId) {
                    Text("None").tag(String?.none)
                    ForEach(viewModel.elements) { el in
                        Text(el.name).tag(String?.some(el.id))
                    }
                }
                .labelsHidden()
                .fixedSize()
                Button {
                    isAddingElement = true
                    newElementName = ""
                } label: {
                    HStack(spacing: 2) {
                        Image(systemName: "plus").font(.system(size: 9))
                        Text("New").font(.system(size: 11))
                    }
                    .foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
    }

    private func commitNewElement() {
        let n = newElementName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        Task {
            if let el = await viewModel.createElement(name: n, kind: nil, description: nil, assignedTo: nil) {
                await MainActor.run {
                    selectedElementId = el.id
                    isAddingElement = false
                    newElementName = ""
                }
            }
        }
    }
}

/// Local-only drafting: nothing is saved or queued until the parent form is submitted.
struct ResearchBriefWizard: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var title: String
    @State private var values: [String: String]
    @State private var step = 0
    @State private var focusRequested = true
    private let preservedContext: String
    let onApply: (String, [String: String], String) -> Void

    static var fields: [KanbanTemplate.TicketField] {
        KanbanTemplate.research.fields + [
            .init(key: "output", label: "Expected output", placeholder: "What would a useful report contain?", kind: .multiLine)
        ]
    }

    init(initialTitle: String, initialValues: [String: String] = [:], existingDescription: String = "",
         onApply: @escaping (String, [String: String], String) -> Void) {
        _title = State(initialValue: initialTitle)
        let parsed = Self.parse(existingDescription)
        _values = State(initialValue: initialValues.isEmpty ? parsed.values : initialValues)
        preservedContext = parsed.context
        self.onApply = onApply
    }

    /// Only recognized section headings are editable fields; all other prose survives.
    static func parse(_ description: String) -> (values: [String: String], context: String) {
        var values: [String: String] = [:]
        var context: [String] = []
        var key: String?
        var fence: String?
        for line in description.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
                let marker = String(trimmed.prefix(3))
                if fence == marker { fence = nil }
                else if fence == nil { fence = marker }
                if let key { values[key, default: ""] += line + "\n" }
                else { context.append(line) }
                continue
            }
            if fence == nil && line.hasPrefix("## ") {
                key = fields.first(where: { "## \($0.label)" == line })?.key
                if key == nil { context.append(line) }
            } else if let key {
                values[key, default: ""] += line + "\n"
            } else {
                context.append(line)
            }
        }
        return (values.mapValues { $0.trimmingCharacters(in: .whitespacesAndNewlines) },
                context.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private var brief: String {
        [preservedContext, KanbanTemplate.composeDescription(fields: Self.fields, values: values)]
            .filter { !$0.isEmpty }.joined(separator: "\n\n")
    }
    private var isReview: Bool { step == Self.fields.count + 1 }
    private var isRequiredStep: Bool {
        step == 0 || (!isReview && ["subject", "questions"].contains(Self.fields[step - 1].key))
    }
    private var canContinue: Bool {
        if step == 0 { return !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if isRequiredStep { return !(values[Self.fields[step - 1].key] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        return true
    }
    private func binding(_ key: String) -> Binding<String> {
        Binding(get: { values[key] ?? "" }, set: { values[key] = $0 })
    }
    static let titleExample = "Compare scheduling tools for a two-location coffee shop"

    /// Keyed by the same stable identities as the fields. A newly added field
    /// simply has no example until one is supplied; reordering cannot swap it.
    static func example(for key: String) -> String? {
        let examples = [
            "subject": "Compare three scheduling tools for a coffee shop with 25 hourly employees.",
            "questions": "1. Which supports shift swaps and break reminders?\n2. What does each cost for 25 employees?\n3. Which integrates with our POS?",
            "why": "Choose a tool to pilot next month and identify the trade-offs before we commit.",
            "constraints": "US products only. Budget: $150/month. Compare the current paid plans. Exclude payroll-only tools.",
            "sources": "Use official pricing pages and product documentation. Link each source and note when pricing needs a quote.",
            "output": "A comparison table, a short recommendation, and a list of unknowns to verify during a demo."
        ]
        return examples[key]
    }

    private var currentExample: String? {
        step == 0 ? Self.titleExample : Self.example(for: Self.fields[step - 1].key)
    }
    private var heading: String {
        if step == 0 { return "What are you researching?" }
        if isReview { return "Review your research brief" }
        return Self.fields[step - 1].label
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label("Research brief", systemImage: "magnifyingglass")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Text("Step \(step + 1) of \(Self.fields.count + 2)")
                    .font(.system(size: 12)).foregroundColor(.secondary)
            }
            ProgressView(value: Double(step + 1), total: Double(Self.fields.count + 2))
                .tint(appState.themeAccent)
            Text(heading).font(.system(size: 23, weight: .semibold))
            if isReview {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(title).font(.system(size: 17, weight: .semibold))
                        if !preservedContext.isEmpty {
                            Text("Existing context").font(.system(size: 12, weight: .semibold))
                            Text(preservedContext).font(.system(size: 13)).textSelection(.enabled)
                        }
                        ForEach(Self.fields) { field in
                            if let value = values[field.key], !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(field.label).font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
                                    Text(value).font(.system(size: 14)).lineSpacing(4).textSelection(.enabled)
                                }
                                .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                                .background(appState.themeText.opacity(0.04)).cornerRadius(8)
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
                Text("Apply returns to the ticket form. Review the assignee and priority there before saving.")
                    .font(.system(size: 12)).foregroundColor(.secondary)
            } else {
                Text(isRequiredStep ? "Required · Be specific enough that someone else can investigate this." : "Optional · Add what you know, or continue to skip this step.")
                    .font(.system(size: 12)).foregroundColor(.secondary)
                ComposerTextView(text: step == 0 ? $title : binding(Self.fields[step - 1].key),
                                 placeholder: step == 0 ? "Name your research ticket…" : Self.fields[step - 1].placeholder,
                                 font: .systemFont(ofSize: 15), textColor: appState.themeText,
                                 minLines: 4, maxLines: 8, submitKey: .commandReturnSends,
                                 focusRequested: $focusRequested)
                    .id(step)
                    .padding(14)
                    .background(appState.themeText.opacity(0.06)).cornerRadius(10)
                if let example = currentExample {
                VStack(alignment: .leading, spacing: 8) {
                    Text("EXAMPLE").font(.system(size: 10, weight: .bold)).foregroundColor(.secondary)
                    Text(example).font(.system(size: 13)).lineSpacing(4)
                    Button("Use this example") {
                        if step == 0 { title = example }
                        else { values[Self.fields[step - 1].key] = example }
                    }
                    .buttonStyle(.borderless)
                    .disabled(step == 0 ? !title.isEmpty : !(values[Self.fields[step - 1].key] ?? "").isEmpty)
                }
                .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .background(appState.themeAccent.opacity(0.07)).cornerRadius(10)
                }
                Spacer(minLength: 0)
            }
            Divider()
            HStack {
                Button("Cancel") { dismiss() }
                Spacer()
                if step > 0 { Button("Back") { step -= 1; focusRequested = true } }
                Button(isReview ? "Apply brief" : "Continue") {
                    if isReview {
                        onApply(title.trimmingCharacters(in: .whitespacesAndNewlines), values, brief)
                        dismiss()
                    } else { step += 1; focusRequested = true }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canContinue)
            }
        }
        .padding(28).frame(width: 620, height: 570)
        .background(Color.appBackground)
    }
}
