import SwiftUI

// MARK: - Sidebar section content

/// Rendered inside the collapsible "Email" sidebar section. Shows a connect
/// prompt when no Gmail is linked, otherwise the unread list — grouped by AI
/// triage bucket once the user runs "Organize with AI". Tapping a row routes
/// the primary detail pane to `EmailDetailView` via `selectedEmailId`.
struct EmailSidebarView: View {
    let searchText: String
    @Environment(AppState.self) private var appState
    private let vm = EmailViewModel.shared

    private var filtered: [EmailMessage] {
        guard !searchText.isEmpty else { return vm.emails }
        let q = searchText.lowercased()
        return vm.emails.filter {
            $0.subject.lowercased().contains(q) || $0.fromAddress.lowercased().contains(q)
        }
    }

    var body: some View {
        VStack(spacing: 2) {
            if !vm.connected {
                connectRow
            } else {
                if vm.isTriaging {
                    infoRow(icon: "sparkles", text: "Organizing…")
                }
                if vm.isLoading && vm.emails.isEmpty {
                    infoRow(icon: "arrow.triangle.2.circlepath", text: "Loading…")
                } else if filtered.isEmpty {
                    infoRow(icon: "tray", text: searchText.isEmpty ? "No unread mail" : "No matches")
                } else {
                    ForEach(vm.grouped(filtered)) { group in
                        if let bucket = group.bucket {
                            bucketHeader(bucket, count: group.emails.count)
                        } else if !vm.triage.isEmpty {
                            unsortedHeader(count: group.emails.count)
                        }
                        ForEach(group.emails) { msg in emailRow(msg) }
                    }
                }
                connectedFooter
            }

            if let err = vm.errorMessage {
                Text(err)
                    .font(.espresso(size: 10))
                    .foregroundColor(.red.opacity(0.85))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 3)
            }
        }
        .padding(.bottom, 6)
        .task { await vm.loadStatus() }
    }

    // MARK: rows

    private var connectRow: some View {
        Button {
            Task { await vm.connect() }
        } label: {
            HStack(spacing: 8) {
                if vm.isConnecting {
                    ProgressView().controlSize(.small)
                    Text("Connecting…")
                } else {
                    Image(systemName: "envelope.badge")
                        .font(.espresso(size: 12))
                        .foregroundColor(appState.themeSidebarAccent)
                    Text("Connect Gmail")
                }
                Spacer()
            }
            .font(.espresso(size: 12))
            .foregroundColor(appState.themeSidebarText)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(vm.isConnecting)
    }

    private func emailRow(_ msg: EmailMessage) -> some View {
        let isSelected = appState.selectedEmailId == msg.id
        return Button {
            selectEmail(msg.id)
        } label: {
            VStack(alignment: .leading, spacing: 1) {
                Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                    .font(.espresso(size: 12, weight: .medium))
                    .foregroundColor(appState.themeSidebarText)
                    .lineLimit(1)
                Text(msg.fromAddress)
                    .font(.espresso(size: 10))
                    .foregroundColor(appState.themeSidebarTextSecondary)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(isSelected ? appState.themeSidebarAccent.opacity(0.10) : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 4)
        .help(vm.triage[msg.id]?.reason ?? "")
    }

    private func bucketHeader(_ bucket: EmailTriageBucket, count: Int) -> some View {
        groupHeader(icon: bucket.icon, title: bucket.label, count: count)
    }

    private func unsortedHeader(count: Int) -> some View {
        groupHeader(icon: "tray", title: "Unsorted", count: count)
    }

    private func groupHeader(icon: String, title: String, count: Int) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon).font(.espresso(size: 9))
            Text(title.uppercased())
                .font(.espresso(size: 9, weight: .semibold))
                .tracking(0.5)
            Text("\(count)").font(.espresso(size: 9))
            Spacer()
        }
        .foregroundColor(appState.themeSidebarTextSecondary)
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 2)
    }

    private func infoRow(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).font(.espresso(size: 10))
            Text(text).font(.espresso(size: 11))
            Spacer()
        }
        .foregroundColor(appState.themeSidebarTextSecondary)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private var connectedFooter: some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark.seal")
                .font(.espresso(size: 9))
                .foregroundColor(appState.themeSidebarAccent)
            Text(vm.email ?? "Connected")
                .font(.espresso(size: 10))
                .foregroundColor(appState.themeSidebarTextSecondary)
                .lineLimit(1)
            Spacer()
            Menu {
                Button {
                    organize()
                } label: {
                    Label(
                        vm.isTriaging ? "Organizing…" : "Organize with AI",
                        systemImage: appState.canEmailAI ? "sparkles" : "lock.fill"
                    )
                }
                .disabled(vm.isTriaging || vm.emails.isEmpty)
                if !vm.triage.isEmpty {
                    Button("Clear groups") { vm.clearTriage() }
                }
                Divider()
                Button("Refresh") { Task { await vm.loadInbox() } }
                Divider()
                Button("Disconnect", role: .destructive) { Task { await vm.disconnect() } }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.espresso(size: 11))
                    .foregroundColor(appState.themeSidebarTextSecondary)
                    .frame(width: 18, height: 18)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Email account options")
        }
        .padding(.horizontal, 12)
        .padding(.top, 4)
    }

    private func organize() {
        guard appState.canEmailAI else {
            appState.presentPaywall(for: "email_ai")
            return
        }
        Task { await vm.organize() }
    }

    /// Email participates in the primary-pane routing chain *after* the
    /// category hubs, so any open hub flag would mask it. Clear everything
    /// first, then set the one destination (same contract as every other
    /// sidebar entry point).
    private func selectEmail(_ id: String) {
        appState.clearPrimaryNav()
        appState.selectedEmailId = id
    }
}

// MARK: - Detail pane

/// Reader for one message plus the AI quick actions: summarize, draft a
/// reply (saved to Gmail drafts, reviewed in `EmailReplySheet` before
/// sending). Resolves from the loaded list, falling back to a fetch by id so
/// a message read elsewhere (or re-opened after relaunch) still opens.
struct EmailDetailView: View {
    let emailId: String
    @Environment(AppState.self) private var appState
    private let vm = EmailViewModel.shared

    @State private var loaded: EmailMessage?
    @State private var isResolving = true
    @State private var summary: String?
    @State private var isSummarizing = false
    @State private var isDrafting = false
    @State private var instructions = ""
    @State private var reply: EmailDraftResponse?
    @State private var actionError: String?
    @State private var sentNote: String?
    @State private var showSendToBoard = false
    /// Bumped whenever the shown message changes, so a slow AI response for
    /// the previous message can't land on this one.
    @State private var generation = 0

    private var msg: EmailMessage? { vm.message(id: emailId) ?? loaded }

    var body: some View {
        Group {
            if let msg {
                content(msg)
            } else if isResolving {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                placeholder
            }
        }
        .background(appState.themeBg)
        .task(id: emailId) {
            generation += 1
            // Drop the previous message first: `msg` falls back to `loaded`,
            // so keeping it would show the old email (with a live action bar)
            // under the new id until the fetch returns.
            loaded = nil
            summary = nil
            actionError = nil
            sentNote = nil
            instructions = ""
            reply = nil
            showSendToBoard = false
            isSummarizing = false
            isDrafting = false
            isResolving = true
            loaded = await vm.ensureMessage(id: emailId)
            isResolving = false
        }
        .sheet(item: $reply) { draft in
            EmailReplySheet(draft: draft, original: msg) {
                sentNote = "Reply sent to \(draft.to)"
            }
        }
    }

    private var placeholder: some View {
        VStack(spacing: 8) {
            Image(systemName: "envelope.open")
                .font(.system(size: 28))
                .foregroundColor(appState.themeTextSecondary)
            Text("This email is no longer available")
                .font(.system(size: 13))
                .foregroundColor(appState.themeTextSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func content(_ msg: EmailMessage) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header(msg)
                if let atts = msg.attachments, !atts.isEmpty {
                    attachmentsRow(atts)
                }
                actionBar(msg)
                if isSummarizing || summary != nil {
                    summaryCard
                }
                Divider().background(appState.themeBorder)
                Text(msg.body)
                    .font(.system(size: 13))
                    .foregroundColor(appState.themeText)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(24)
            .frame(maxWidth: 780, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .sheet(isPresented: $showSendToBoard) {
            EmailSendToBoardSheet(emails: [msg]) { board in
                actionError = nil
                sentNote = "Email card created on \(board)"
            }
        }
    }

    private func header(_ msg: EmailMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .textSelection(.enabled)
                Spacer(minLength: 8)
                Button {
                    showSendToBoard = true
                } label: {
                    Label("Send to board", systemImage: "rectangle.stack.badge.plus")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .help("Create an Email card with this message attached, for you or AutoPR to work")
            }
            HStack(alignment: .firstTextBaseline) {
                Text(msg.fromAddress)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(appState.themeTextSecondary)
                    .textSelection(.enabled)
                Spacer()
                Text(msg.date)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    private func attachmentsRow(_ atts: [EmailAttachment]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(atts, id: \.attachmentId) { att in
                    Label(att.filename, systemImage: "paperclip")
                        .font(.system(size: 11))
                        .lineLimit(1)
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(appState.themeCard)
                        .cornerRadius(5)
                }
            }
        }
        .help("Attachments stay in Gmail")
    }

    // MARK: AI action bar

    private func actionBar(_ msg: EmailMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeAccent)
                TextField("Reply instructions (optional)…", text: $instructions)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .frame(maxWidth: .infinity)
                    .onSubmit { draft(msg) }
                    .help("e.g. \"say yes to Friday, keep it short\"")
                actionButton("Summarize", icon: "text.alignleft", busy: isSummarizing) { summarize(msg) }
                actionButton("Draft reply", icon: "arrowshape.turn.up.left", busy: isDrafting, primary: true) { draft(msg) }
            }
            if let actionError {
                statusLine(icon: "exclamationmark.triangle.fill", text: actionError, color: .orange)
            } else if let sentNote {
                statusLine(icon: "checkmark.circle.fill", text: sentNote, color: .green)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(appState.themeAccent.opacity(0.06))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(appState.themeAccent.opacity(0.25), lineWidth: 1)
        )
        .cornerRadius(6)
    }

    private func actionButton(
        _ title: String,
        icon: String,
        busy: Bool,
        primary: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if busy {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: appState.canEmailAI ? icon : "lock.fill")
                        .font(.system(size: 10))
                }
                Text(title).font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(primary ? appState.themeOnAccent : appState.themeAccent)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(primary ? appState.themeAccent : appState.themeAccent.opacity(0.12))
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .help(appState.canEmailAI ? "" : "Email AI needs Lite")
    }

    private func statusLine(icon: String, text: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9)).foregroundColor(color)
            Text(text).font(.system(size: 10)).foregroundColor(color)
            Spacer()
        }
    }

    private var summaryCard: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "sparkles")
                .font(.system(size: 11))
                .foregroundColor(appState.themeAccent)
                .padding(.top, 1)
            if isSummarizing {
                Text("Summarizing…")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
            } else {
                let text = summary ?? ""
                Text(text.isEmpty ? "Summary unavailable — try again." : text)
                    .font(.system(size: 12))
                    .foregroundColor(text.isEmpty ? appState.themeTextSecondary : appState.themeText)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Spacer(minLength: 0)
            if !isSummarizing {
                Button {
                    summary = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Hide summary")
            }
        }
        .padding(12)
        .background(appState.themeAccent.opacity(0.05))
        .cornerRadius(6)
    }

    // MARK: actions

    private func requireEmailAI() -> Bool {
        guard appState.canEmailAI else {
            appState.presentPaywall(for: "email_ai")
            return false
        }
        return true
    }

    private func summarize(_ msg: EmailMessage) {
        guard requireEmailAI(), !isSummarizing else { return }
        isSummarizing = true
        actionError = nil
        let gen = generation
        let id = msg.id
        Task {
            do {
                let resp = try await EmailService.shared.summarize(emailId: id)
                guard gen == generation else { return }
                summary = resp.summary.trimmingCharacters(in: .whitespacesAndNewlines)
            } catch {
                guard gen == generation else { return }
                actionError = error.localizedDescription
            }
            if gen == generation { isSummarizing = false }
        }
    }

    private func draft(_ msg: EmailMessage) {
        guard requireEmailAI(), !isDrafting else { return }
        isDrafting = true
        actionError = nil
        sentNote = nil
        let gen = generation
        let id = msg.id
        let text = instructions
        Task {
            do {
                let resp = try await EmailService.shared.draftReply(emailId: id, instructions: text)
                guard gen == generation else { return }
                reply = resp
            } catch {
                guard gen == generation else { return }
                actionError = error.localizedDescription
            }
            if gen == generation { isDrafting = false }
        }
    }
}
