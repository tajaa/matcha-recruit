import SwiftUI

// MARK: - Staged outreach
//
// A research run can propose an email, a contact, or a review request. The
// harness never sends one — every proposal arrives here as `pending`, and this
// section is the only place a person can turn one into a real send.
//
// Two deliberate refusals in this UI:
//   • no "approve all" — the rule is a human reads and approves each item, and
//     a bulk control is exactly how that rule gets bypassed in practice;
//   • "Send" appears only on an `email`. A contact or review request is
//     something a person does, so those offer "Mark handled" instead. Letting
//     them read as `sent` would put this system's name on an act it never
//     performed.

extension TaskViewerSheet {

    @ViewBuilder
    var outreachSection: some View {
        if !stagedActions.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "paperplane")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    Text("PROPOSED OUTREACH")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                        .tracking(0.5)
                    Text("\(stagedActions.filter(\.isPending).count) pending")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeText.opacity(0.08))
                        .cornerRadius(4)
                }
                Text("Drafted by AutoPR. Nothing is sent until you approve it, and it sends from your own mailbox.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                ForEach(stagedActions) { action in
                    stagedActionRow(action)
                }
                if let error = stagedActionError {
                    Text(error)
                        .font(.system(size: 10))
                        .foregroundColor(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    @ViewBuilder
    private func stagedActionRow(_ action: MWStagedAction) -> some View {
        let busy = resolvingActionId == action.id
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(Self.outreachKindLabel(action.kind))
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.4)
                    .foregroundColor(.mwInkStrong)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Color.mwInkStrong.opacity(0.14))
                    .cornerRadius(3)
                Text(action.to)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer(minLength: 0)
                if !action.isPending {
                    Text(Self.outreachStateLabel(action))
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(action.state == "failed" ? .red : .secondary)
                }
            }
            Text(action.subject)
                .font(.system(size: 11))
                .foregroundColor(appState.themeText.opacity(0.9))
                .fixedSize(horizontal: false, vertical: true)
            // The whole body, never an excerpt: approving is agreeing to send
            // this exact text, so all of it has to be on screen first.
            Text(action.body)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(appState.themeText.opacity(0.05))
                .cornerRadius(4)
            Text("Why: \(action.why)")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if action.isPending {
                HStack(spacing: 8) {
                    if action.isSendable {
                        Button {
                            Task { await sendStagedAction(action) }
                        } label: {
                            Label(busy ? "Sending…" : "Send", systemImage: "paperplane.fill")
                                .font(.system(size: 10, weight: .semibold))
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(busy)
                        .help("Send this exact text from your own Gmail")
                    }
                    Button("Mark handled") {
                        Task { await resolveStagedAction(action, state: "handled") }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .disabled(busy)
                    .help("You did this yourself — close it without sending anything")
                    Button("Dismiss") {
                        Task { await resolveStagedAction(action, state: "dismissed") }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .disabled(busy)
                    .help("This will not be done")
                    if busy { ProgressView().controlSize(.small) }
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(appState.themeText.opacity(action.isPending ? 0.06 : 0.03))
        .cornerRadius(6)
        .opacity(action.isPending ? 1 : 0.65)
    }

    static func outreachKindLabel(_ kind: String) -> String {
        switch kind {
        case "email": return "EMAIL"
        case "contact": return "CONTACT"
        case "review_request": return "REVIEW"
        default: return kind.uppercased()
        }
    }

    /// Who did what, kept literal. "Sent" is claimed only for mail this system
    /// actually delivered.
    static func outreachStateLabel(_ action: MWStagedAction) -> String {
        let who = action.resolvedByName.map { " · \($0)" } ?? ""
        switch action.state {
        case "sent": return "Sent\(who)"
        case "handled": return "Handled\(who)"
        case "dismissed": return "Dismissed\(who)"
        case "failed": return "Send failed"
        default: return action.state
        }
    }

    // MARK: - Actions

    func loadStagedActions() async {
        guard let pid = viewModel.project?.id else { return }
        do {
            stagedActions = try await MatchaWorkService.shared.listStagedActions(
                projectId: pid, taskId: task.id
            )
            stagedActionError = nil
        } catch {
            // A ticket with no proposals is the common case and 404s nothing;
            // a real failure should not blank the section silently.
            stagedActionError = error.localizedDescription
        }
    }

    func sendStagedAction(_ action: MWStagedAction) async {
        guard let pid = viewModel.project?.id, resolvingActionId == nil else { return }
        resolvingActionId = action.id
        stagedActionError = nil
        defer { resolvingActionId = nil }
        do {
            _ = try await MatchaWorkService.shared.sendStagedAction(
                projectId: pid, taskId: task.id, actionId: action.id
            )
        } catch {
            stagedActionError = error.localizedDescription
        }
        // Reload either way: the server owns the outcome, and after a failed
        // send the row may already be resolved on its side.
        await loadStagedActions()
    }

    func resolveStagedAction(_ action: MWStagedAction, state: String) async {
        guard let pid = viewModel.project?.id, resolvingActionId == nil else { return }
        resolvingActionId = action.id
        stagedActionError = nil
        defer { resolvingActionId = nil }
        do {
            _ = try await MatchaWorkService.shared.resolveStagedAction(
                projectId: pid, taskId: task.id, actionId: action.id, state: state
            )
        } catch {
            stagedActionError = error.localizedDescription
        }
        await loadStagedActions()
    }
}
