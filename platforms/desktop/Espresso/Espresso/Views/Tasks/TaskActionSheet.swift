import SwiftUI
import AppKit

/// One action on a finding (buy it, book it), start to end: its own fields,
/// then exactly what it will do, then the person's yes, then what came of
/// it. The server proposes and carries out; this only shows and asks.
@Observable @MainActor
final class TaskActionFlow: Identifiable {
    enum Stage: Equatable { case details, review, finished }

    let taskId: String
    let itemId: String
    let itemTitle: String
    let action: AgentTaskAction
    var values: [String: String] = [:]
    var run: AgentTaskActionRun?
    var busy = false
    var errorMessage: String?

    private let service = AgentTaskService.shared

    nonisolated var id: String { "\(itemId)|\(action.key)" }

    init(taskId: String, itemId: String, itemTitle: String, action: AgentTaskAction) {
        self.taskId = taskId; self.itemId = itemId; self.itemTitle = itemTitle; self.action = action
        for field in action.params where !field.initial.isEmpty { values[field.key] = field.initial }
    }

    var stage: Stage { TaskActionFlow.stageFor(run) }

    /// Ask the server what it would do. Nothing happens yet.
    func review() async {
        guard !busy else { return }
        busy = true; errorMessage = nil
        defer { busy = false }
        do {
            run = try await service.proposeAction(taskId, itemId, action: action.key,
                                                  params: TaskActionFlow.params(values, fields: action.params))
        } catch { report(error) }
    }

    /// The yes: carried out once. Returns the link to open, if it made one.
    func confirm() async -> URL? {
        guard let proposal = run, proposal.isProposed, !busy else { return nil }
        busy = true; errorMessage = nil
        defer { busy = false }
        do {
            run = try await service.confirmAction(proposal.id)
            return run?.status == "done" ? TasksViewModel.webURL(run?.result?.url) : nil
        } catch {
            report(error)
            return nil
        }
    }

    /// The person said no (or closed it before deciding).
    func cancel() async {
        guard let proposal = run, proposal.isProposed else { return }
        run = try? await service.cancelAction(proposal.id)
    }

    /// Back to the fields, to change them.
    func edit() async {
        await cancel()
        run = nil
    }

    private func report(_ error: Error) {
        errorMessage = (error as? APIError).map { AssistantText.message(for: $0) } ?? error.localizedDescription
    }

    // MARK: Pure helpers (tested)

    nonisolated static func stageFor(_ run: AgentTaskActionRun?) -> Stage {
        guard let run else { return .details }
        return run.isProposed ? .review : .finished
    }

    /// What the person typed for the action's own fields, trimmed; blanks left out.
    nonisolated static func params(_ values: [String: String], fields: [IntakeFormField]) -> [String: String] {
        var out: [String: String] = [:]
        for field in fields {
            let value = (values[field.key] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !value.isEmpty { out[field.key] = value }
        }
        return out
    }
}

struct TaskActionSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    let flow: TaskActionFlow
    let onFinished: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Image(systemName: flow.action.systemImage).foregroundColor(appState.themeAccent)
                Text(flow.run?.preview?.title.isEmpty == false ? flow.run!.preview!.title
                     : "\(flow.action.label) \(flow.itemTitle)")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(2)
            }
            switch flow.stage {
            case .details: details
            case .review: review
            case .finished: finished
            }
            if let error = flow.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(20)
        .frame(width: 440)
        .task {
            // Nothing to fill in: straight to what it would do.
            if flow.action.params.isEmpty && flow.run == nil { await flow.review() }
        }
        // Closed before deciding: the proposal is withdrawn, not left waiting.
        .onDisappear { if flow.stage == .review { Task { await flow.cancel() } } }
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(flow.action.description)
                .font(.system(size: 12))
                .foregroundColor(appState.themeTextSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(flow.action.params) { field in
                VStack(alignment: .leading, spacing: 4) {
                    Text(field.label).font(.system(size: 11, weight: .semibold)).foregroundColor(appState.themeText)
                    IntakeFieldInput(field: field, value: Binding(
                        get: { flow.values[field.key] ?? "" }, set: { flow.values[field.key] = $0 }))
                    if !field.help.isEmpty {
                        Text(field.help).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    }
                }
            }
            HStack {
                Button("Cancel") { dismiss() }
                Spacer()
                if flow.busy { ProgressView().controlSize(.small) }
                Button("Review") { Task { await flow.review() } }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                    .disabled(flow.busy)
            }
        }
    }

    private var review: some View {
        VStack(alignment: .leading, spacing: 12) {
            lines(flow.run?.preview?.lines ?? [])
            if let note = flow.run?.preview?.note, !note.isEmpty {
                Text(note)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Button("Cancel") { Task { await flow.cancel(); dismiss() } }
                if !flow.action.params.isEmpty {
                    Button("Change") { Task { await flow.edit() } }
                }
                Spacer()
                if flow.busy { ProgressView().controlSize(.small) }
                Button(flow.run?.confirmLabel ?? flow.action.confirmLabel) {
                    Task {
                        if let url = await flow.confirm() { NSWorkspace.shared.open(url) }
                        onFinished()
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .keyboardShortcut(.defaultAction)
                .disabled(flow.busy)
            }
        }
    }

    private var finished: some View {
        VStack(alignment: .leading, spacing: 12) {
            if flow.run?.status == "done", let result = flow.run?.result {
                Label(result.headline, systemImage: "checkmark.circle.fill")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.green)
                lines(result.lines)
            } else {
                Label(flow.run?.error ?? "It didn't go through. Nothing was done.", systemImage: "xmark.octagon")
                    .font(.system(size: 12))
                    .foregroundColor(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                if let url = TasksViewModel.webURL(flow.run?.result?.url) {
                    Button { NSWorkspace.shared.open(url) } label: {
                        Label("Open again", systemImage: "arrow.up.right.square")
                    }
                }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
    }

    private func lines(_ lines: [AgentTaskActionLine]) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                GridRow {
                    Text(line.label)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                    Text(line.value)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }
        }
    }
}
