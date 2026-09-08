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
        // The error belongs to the section, so the section has to survive an
        // empty list: with `!stagedActions.isEmpty` alone a failed load hid the
        // very message that says the load failed, and "this ticket has no
        // proposals" and "we could not find out" looked identical.
        if !stagedActions.isEmpty || stagedActionError != nil {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "paperplane")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    Text("PROPOSED OUTREACH")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                        .tracking(0.5)
                    Text("\(stagedActions.filter(\.isOpen).count) open")
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
                if let sent = stagedActionSentTo {
                    Label("Sent to \(sent) from your Gmail.", systemImage: "checkmark.circle")
                        .font(.system(size: 10))
                        .foregroundColor(.matcha600)
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
                        .foregroundColor(action.isFailed || action.isInterrupted ? .red : .secondary)
                }
            }
            if action.isFailed, let detail = action.detail, !detail.isEmpty {
                // The provider's own words — the only thing that tells the
                // approver whether to retry or to fix something first.
                Text(detail)
                    .font(.system(size: 10))
                    .foregroundColor(.red)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
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
            if action.isOpen {
                HStack(spacing: 8) {
                    if action.isSendable, action.canRetry {
                        if gmailConnected == false {
                            // Discovered here, not by pressing Send and reading
                            // an HTTP 400. Same OAuth flow as the Email panel.
                            Button {
                                Task { await connectGmailForOutreach() }
                            } label: {
                                Label(connectingGmail ? "Opening Google…" : "Connect Gmail to send",
                                      systemImage: "envelope.badge")
                                    .font(.system(size: 10, weight: .semibold))
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .disabled(connectingGmail)
                            .help("Mail goes out from your own mailbox, so it has to be connected first")
                        } else {
                            Button {
                                Task { await sendStagedAction(action) }
                            } label: {
                                Label(busy ? "Sending…" : (action.isFailed ? "Retry send" : "Send"),
                                      systemImage: "paperplane.fill")
                                    .font(.system(size: 10, weight: .semibold))
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                            .disabled(busy)
                            .help("Send this exact text from your own Gmail")
                        }
                    }
                    if action.canClose {
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
                    }
                    if busy { ProgressView().controlSize(.small) }
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(appState.themeText.opacity(action.isOpen ? 0.06 : 0.03))
        .cornerRadius(6)
        .opacity(action.isOpen ? 1 : 0.65)
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
        // A claim with no outcome row. The send either never returned or the
        // process died holding it — either way this system must not say "Sent".
        if action.isInterrupted { return "Send interrupted — check your mailbox" }
        switch action.state {
        case "sent": return "Sent\(who)"
        case "handled": return "Handled\(who)"
        case "dismissed": return "Dismissed\(who)"
        case "failed": return "Send failed"
        default: return action.state
        }
    }

    // MARK: - Actions

    /// "HTTP 400: Connect your Gmail…" is an implementation detail; the
    /// sentence after the colon is what the approver needs.
    static func outreachErrorText(_ error: Error) -> String {
        if case APIError.httpError(_, let message) = error { return message }
        return error.localizedDescription
    }

    /// `keepingError` is how a failed send survives the reload that follows it:
    /// a successful list call clears the banner, which would otherwise wipe the
    /// only place the send's own failure was reported.
    func loadStagedActions(keepingError: String? = nil) async {
        guard let pid = viewModel.project?.id else { return }
        do {
            stagedActions = try await MatchaWorkService.shared.listStagedActions(
                projectId: pid, taskId: task.id
            )
            stagedActionError = keepingError
        } catch APIError.httpError(404, _) {
            // A backend that predates this feature (or a proxy in front of it)
            // answers 404. That is "no proposals", not a red banner on every
            // ticket in the company until the next deploy.
            stagedActions = []
            stagedActionError = keepingError
        } catch {
            // A real failure should not blank the section silently.
            stagedActionError = keepingError ?? Self.outreachErrorText(error)
        }
        // Only ask about Gmail when there is something to send; the answer
        // decides whether the row offers Send or Connect.
        if stagedActions.contains(where: { $0.isSendable && $0.canRetry }), gmailConnected == nil {
            await loadGmailStatusForOutreach()
        }
    }

    func loadGmailStatusForOutreach() async {
        do {
            gmailConnected = try await MatchaWorkService.shared.agentEmailStatus().connected
        } catch {
            // Unknown stays unknown: the server re-checks on send anyway, and
            // its message names the fix.
            gmailConnected = nil
        }
    }

    /// Same flow as the Email panel: open Google's consent page, then poll the
    /// status once the user has had time to finish.
    func connectGmailForOutreach() async {
        guard !connectingGmail else { return }
        connectingGmail = true
        defer { connectingGmail = false }
        do {
            let authUrl = try await MatchaWorkService.shared.agentConnectGmail()
            if let url = URL(string: authUrl) { SafeURL.open(url) }
            try? await Task.sleep(for: .seconds(5))
            await loadGmailStatusForOutreach()
        } catch {
            stagedActionError = Self.outreachErrorText(error)
        }
    }

    func sendStagedAction(_ action: MWStagedAction) async {
        guard let pid = viewModel.project?.id, resolvingActionId == nil else { return }
        resolvingActionId = action.id
        stagedActionError = nil
        stagedActionSentTo = nil
        defer { resolvingActionId = nil }
        var sendError: String?
        do {
            let result = try await MatchaWorkService.shared.sendStagedAction(
                projectId: pid, taskId: task.id, actionId: action.id
            )
            stagedActionSentTo = result.to ?? action.to
        } catch {
            sendError = Self.outreachErrorText(error)
            // The server's own verdict on the mailbox wins over a cached one.
            if sendError?.localizedCaseInsensitiveContains("gmail") == true { gmailConnected = false }
        }
        // Reload either way: the server owns the outcome, and after a failed
        // send it has already written the `failed` row this will show.
        await loadStagedActions(keepingError: sendError)
        // The timeline gained a "Sent to …" note in the approver's name.
        if sendError == nil { await loadHistory() }
    }

    func resolveStagedAction(_ action: MWStagedAction, state: String) async {
        guard let pid = viewModel.project?.id, resolvingActionId == nil else { return }
        resolvingActionId = action.id
        stagedActionError = nil
        stagedActionSentTo = nil
        defer { resolvingActionId = nil }
        var resolveError: String?
        do {
            _ = try await MatchaWorkService.shared.resolveStagedAction(
                projectId: pid, taskId: task.id, actionId: action.id, state: state
            )
        } catch {
            resolveError = Self.outreachErrorText(error)
        }
        await loadStagedActions(keepingError: resolveError)
    }
}
