import SwiftUI

/// "New Deal" form for sales-pipeline columns. Captures structured deal fields
/// (value, contact, expected close, outcome) on creation — persisted via the
/// create route, which already accepts them — instead of a bare title quick-add.
/// Mirrors TaskComposeContent's chrome; field styling matches TaskEditorSheet's
/// salesSection.
struct DealComposeContent: View {
    @Environment(AppState.self) private var appState
    /// Pipeline stage column key (lead/qualified/…) the deal is created into.
    let stageKey: String
    let stageLabel: String
    @Bindable var viewModel: ProjectDetailViewModel
    let onClose: () -> Void

    @State private var title = ""
    @State private var dealValue = ""
    @State private var probability: String
    @State private var contactCompany = ""
    @State private var contactName = ""
    @State private var contactEmail = ""
    @State private var contactPhone = ""
    @State private var expectedClose = ""
    @State private var outcome = "open"
    @State private var lossReason = ""
    @State private var nextActionAt = ""
    @State private var assignedTo: String?
    @State private var saving = false

    init(stageKey: String, stageLabel: String, viewModel: ProjectDetailViewModel, onClose: @escaping () -> Void) {
        self.stageKey = stageKey
        self.stageLabel = stageLabel
        self.viewModel = viewModel
        self.onClose = onClose
        // Prefill win-probability from the stage's default so the forecast is
        // sane before the user touches it.
        _probability = State(initialValue: SalesStage.defaultProbability[stageKey].map(String.init) ?? "")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "dollarsign.circle")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeAccent)
                Text("New Deal — \(stageLabel)")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
            }

            TextField("Deal name", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText)
                .padding(8)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(6)

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    VStack(alignment: .leading, spacing: 8) {
                        dealLabel("DEAL")
                        HStack(spacing: 8) {
                            dealField("Value ($)", text: $dealValue)
                            dealField("Win %", text: $probability)
                        }
                        HStack(spacing: 8) {
                            dealField("Company", text: $contactCompany)
                            dealField("Contact", text: $contactName)
                        }
                        HStack(spacing: 8) {
                            dealField("Email", text: $contactEmail)
                            dealField("Phone", text: $contactPhone)
                        }
                        dealField("Expected close (YYYY-MM-DD)", text: $expectedClose)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        dealLabel("OUTCOME")
                        Picker("", selection: $outcome) {
                            Text("Open").tag("open")
                            Text("Won").tag("won")
                            Text("Lost").tag("lost")
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                        if outcome == "lost" {
                            dealField("Loss reason", text: $lossReason)
                        }
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        dealLabel("FOLLOW-UP")
                        dealField("Next action (YYYY-MM-DD)", text: $nextActionAt)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(maxHeight: 320)

            if !viewModel.collaborators.isEmpty {
                HStack(spacing: 6) {
                    Text("Owner")
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
                Button("Add Deal") { submit() }
                    .buttonStyle(.plain)
                    .foregroundColor(.matcha500)
                    .disabled(saving || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 420)
        .glassPanel(cornerRadius: 0, material: .hudWindow, blending: .behindWindow,
                    tint: Color.appBackground, tintOpacity: 0.62, shadow: false)
    }

    private func dealLabel(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(.matcha500)
            .tracking(0.5)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func dealField(_ placeholder: String, text: Binding<String>) -> some View {
        TextField(placeholder, text: text)
            .textFieldStyle(.plain)
            .font(.system(size: 12))
            .foregroundColor(appState.themeText)
            .padding(7)
            .background(appState.themeText.opacity(0.06))
            .cornerRadius(5)
    }

    private func submit() {
        let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !saving else { return }
        saving = true
        func clean(_ s: String) -> String? {
            let v = s.trimmingCharacters(in: .whitespacesAndNewlines)
            return v.isEmpty ? nil : v
        }
        Task {
            await viewModel.addTask(
                title: t,
                column: "todo",
                pipelineColumn: stageKey,
                assignedTo: assignedTo,
                category: "sales",
                dealValue: clean(dealValue).flatMap(Double.init),
                probability: clean(probability).flatMap(Int.init),
                contactName: clean(contactName),
                contactCompany: clean(contactCompany),
                contactEmail: clean(contactEmail),
                contactPhone: clean(contactPhone),
                outcome: outcome,
                lossReason: outcome == "lost" ? clean(lossReason) : nil,
                nextActionAt: clean(nextActionAt),
                expectedClose: clean(expectedClose)
            )
            onClose()
        }
    }
}
