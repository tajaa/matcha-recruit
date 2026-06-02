import SwiftUI

/// One editable AI-suggested checklist step. Local Identifiable row (UUID)
/// so editing/removing stays stable; mapped back to [String] on Create.
struct DraftStep: Identifiable, Equatable {
    let id = UUID()
    var text: String
}

/// Reviews a Gemini-drafted ticket before it's created. Every field is editable
/// (the AI can be wrong about assignee/priority); "Create" routes through the
/// normal task-create path. Decoupled from any view model — the board and the
/// chat "Create ticket" flow both present it with their own picker data + create closure.
struct AIDraftReviewSheet: View {
    @Environment(AppState.self) private var appState
    let draft: MWTaskDraft
    /// Picker options. Empty (e.g. when launched from a chat) just hides the
    /// assignee/element pickers — the AI's resolved values still apply.
    let collaborators: [MWProjectCollaborator]
    let elements: [MWProjectElement]
    /// Create the task. The board wires this to `addTask` (optimistic insert);
    /// the chat path wires it straight to the create endpoint.
    let onCreate: (_ title: String, _ column: String, _ priority: String, _ assignedTo: String?, _ description: String?, _ category: String, _ elementId: String?, _ subtasks: [String]?) async -> Void
    let onClose: () -> Void

    @State private var title: String
    @State private var description: String
    @State private var priority: String
    @State private var category: String
    @State private var boardColumn: String
    @State private var assignedTo: String?
    @State private var selectedElementId: String?
    @State private var creating = false
    @State private var steps: [DraftStep]
    @State private var newStep = ""

    private let priorities = ["critical", "high", "medium", "low"]
    private let categories = ["manual", "engineering", "bug", "product", "sales", "general", "feat", "fix"]

    init(
        draft: MWTaskDraft,
        collaborators: [MWProjectCollaborator],
        elements: [MWProjectElement],
        onCreate: @escaping (_ title: String, _ column: String, _ priority: String, _ assignedTo: String?, _ description: String?, _ category: String, _ elementId: String?, _ subtasks: [String]?) async -> Void,
        onClose: @escaping () -> Void
    ) {
        self.draft = draft
        self.collaborators = collaborators
        self.elements = elements
        self.onCreate = onCreate
        self.onClose = onClose
        _title = State(initialValue: draft.title)
        _description = State(initialValue: draft.description ?? "")
        _priority = State(initialValue: draft.priority)
        _category = State(initialValue: draft.category)
        _boardColumn = State(initialValue: draft.boardColumn)
        _assignedTo = State(initialValue: draft.assignedTo)
        _selectedElementId = State(initialValue: draft.elementId)
        _steps = State(initialValue: (draft.subtasks ?? []).map { DraftStep(text: $0) })
    }

    /// Editable checklist of AI-suggested steps. Rows can be edited, removed, or
    /// appended; cleaned to non-empty [String] on Create.
    @ViewBuilder
    private var checklistEditor: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: "checklist").font(.system(size: 10)).foregroundColor(appState.themeAccent)
                Text("CHECKLIST").font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary).tracking(0.5)
                if !steps.isEmpty {
                    Text("\(steps.count)").font(.system(size: 9)).foregroundColor(.secondary)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(appState.themeText.opacity(0.08)).cornerRadius(4)
                }
                Spacer()
            }
            ForEach($steps) { $step in
                HStack(spacing: 6) {
                    Image(systemName: "circle").font(.system(size: 9)).foregroundColor(.secondary)
                    TextField("Step", text: $step.text)
                        .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(appState.themeText)
                    Button { steps.removeAll { $0.id == step.id } } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 10)).foregroundColor(.secondary)
                    }.buttonStyle(.plain)
                }
            }
            HStack(spacing: 6) {
                Image(systemName: "plus").font(.system(size: 9)).foregroundColor(.secondary)
                TextField("Add a step…", text: $newStep)
                    .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(appState.themeText)
                    .onSubmit { addStep() }
            }
        }
        .padding(8)
        .background(appState.themeText.opacity(0.05))
        .cornerRadius(6)
    }

    private func addStep() {
        let t = newStep.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        steps.append(DraftStep(text: t))
        newStep = ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles").font(.system(size: 12)).foregroundColor(appState.themeAccent)
                Text("Review AI ticket").font(.system(size: 14, weight: .semibold)).foregroundColor(appState.themeText)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark").font(.system(size: 11)).foregroundColor(.secondary)
                }.buttonStyle(.plain)
            }

            TextField("Title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText)
                .padding(8)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(6)

            TextEditor(text: $description)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText.opacity(0.9))
                .scrollContentBackground(.hidden)
                .padding(6)
                .frame(height: 180)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(6)

            HStack(spacing: 6) {
                labeledPicker("Priority", selection: $priority, options: priorities)
                labeledPicker("Type", selection: $category, options: categories)
                Spacer()
            }
            HStack(spacing: 6) {
                Text("Column").font(.system(size: 11)).foregroundColor(.secondary)
                Picker("", selection: $boardColumn) {
                    ForEach(kanbanColumns, id: \.key) { c in Text(c.label).tag(c.key) }
                }.labelsHidden().fixedSize()
                Spacer()
            }

            if !collaborators.isEmpty {
                HStack(spacing: 6) {
                    Text("Assignee").font(.system(size: 11)).foregroundColor(.secondary)
                    Picker("", selection: $assignedTo) {
                        Text("Unassigned").tag(String?.none)
                        ForEach(collaborators) { c in
                            Text(c.name).tag(String?.some(c.userId))
                        }
                    }.labelsHidden().fixedSize()
                    Spacer()
                }
            }
            if !elements.isEmpty {
                HStack(spacing: 6) {
                    Text("Element").font(.system(size: 11)).foregroundColor(.secondary)
                    Picker("", selection: $selectedElementId) {
                        Text("None").tag(String?.none)
                        ForEach(elements) { el in
                            Text(el.name).tag(String?.some(el.id))
                        }
                    }.labelsHidden().fixedSize()
                    Spacer()
                }
            }

            checklistEditor

            HStack {
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain).foregroundColor(.secondary)
                Spacer()
                Button {
                    let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !t.isEmpty else { return }
                    creating = true
                    let desc = description.trimmingCharacters(in: .whitespacesAndNewlines)
                    let cleanedSteps = steps
                        .map { $0.text.trimmingCharacters(in: .whitespacesAndNewlines) }
                        .filter { !$0.isEmpty }
                    Task {
                        await onCreate(
                            t, boardColumn, priority, assignedTo,
                            desc.isEmpty ? nil : desc,
                            category, selectedElementId,
                            cleanedSteps.isEmpty ? nil : cleanedSteps
                        )
                        onClose()
                    }
                } label: {
                    if creating { ProgressView().controlSize(.small) }
                    else { Text("Create").font(.system(size: 12, weight: .semibold)).foregroundColor(.matcha500) }
                }
                .buttonStyle(.plain)
                .disabled(creating || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 440)
        .background(Color.appBackground)
    }

    private func labeledPicker(_ label: String, selection: Binding<String>, options: [String]) -> some View {
        HStack(spacing: 4) {
            Text(label).font(.system(size: 11)).foregroundColor(.secondary)
            Picker("", selection: selection) {
                ForEach(options, id: \.self) { Text($0.capitalized).tag($0) }
            }.labelsHidden().fixedSize()
        }
    }
}
