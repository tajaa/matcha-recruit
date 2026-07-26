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
    /// One entry per `template.fields` element, keyed by field.key. Composed
    /// into the markdown description on Add.
    @State private var fieldValues: [String: String] = [:]
    @State private var priority: String
    @State private var assignedTo: String?
    @State private var selectedElementId: String?
    @State private var isAddingElement = false
    @State private var newElementName = ""

    init(column: String, template: KanbanTemplate, viewModel: ProjectDetailViewModel, onClose: @escaping () -> Void) {
        self.column = column
        self.template = template
        self.viewModel = viewModel
        self.onClose = onClose
        _priority = State(initialValue: template.defaultPriority)
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

            TextField("Title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText)
                .padding(8)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(6)

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(template.fields) { field in
                        fieldEditor(for: field)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(maxHeight: 300)

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

            HStack {
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add") {
                    let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !t.isEmpty else { return }
                    let desc = KanbanTemplate.composeDescription(
                        fields: template.fields, values: fieldValues
                    )
                    Task {
                        await viewModel.addTask(
                            title: t, column: column, priority: priority,
                            assignedTo: assignedTo,
                            description: desc.isEmpty ? nil : desc,
                            category: template.rawValue,
                            elementId: selectedElementId
                        )
                        onClose()
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(.matcha500)
                .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 420)
        .glassPanel(cornerRadius: 0, material: .hudWindow, blending: .behindWindow,
                    tint: Color.appBackground, tintOpacity: 0.62, shadow: false)
    }

    /// Renders one structured field (labeled). Single-line → TextField,
    /// multi-line → TextEditor with a placeholder overlay (TextEditor has no
    /// native placeholder), picker → segmented dropdown with an empty "—" tag.
    @ViewBuilder
    private func fieldEditor(for field: KanbanTemplate.TicketField) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(field.label.uppercased())
                .font(.system(size: 9, weight: .semibold))
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
                TextEditor(text: fieldBinding(field.key))
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.9))
                    .scrollContentBackground(.hidden)
                    .padding(5)
                    .frame(height: 60)
                    .background(appState.themeText.opacity(0.06))
                    .cornerRadius(5)
                    .overlay(alignment: .topLeading) {
                        if (fieldValues[field.key] ?? "").isEmpty && !field.placeholder.isEmpty {
                            Text(field.placeholder)
                                .font(.system(size: 12))
                                .foregroundColor(.secondary.opacity(0.55))
                                .padding(.horizontal, 9)
                                .padding(.top, 11)
                                .allowsHitTesting(false)
                        }
                    }
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
