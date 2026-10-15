import SwiftUI
import AppKit

/// A person's private conversation with Espresso.
///
/// It is a channel underneath, so the messages, the cards and the quick
/// replies are the chat's own (`ChannelDetailView`). What this adds is the way
/// in (named conversations, created separately) and the sheet where
/// abilities are switched on. Every message here is addressed to Espresso: no
/// mention is needed.
struct AssistantView: View {
    var acceptsEmailHandoff = false
    @Environment(AppState.self) private var appState
    @State private var channelId: String?
    @State private var conversations: [AssistantConversation] = []
    @State private var hasMore = false
    @State private var operations = AssistantOperationQueue()
    private var loading: Bool { operations.loading }
    @State private var errorMessage: String?
    @State private var showAbilities = false
    @State private var showEditor = false
    @State private var editing: AssistantConversation?
    @State private var title = ""
    @State private var createKey = UUID()
    @State private var initialDraft = ""
    @State private var sessionSearch = ""
    @State private var showSessionPicker = false

    private var selectionKey: String { "assistant.conversation.\(appState.currentUser?.id ?? "")" }

    var body: some View {
        GeometryReader { geometry in
            let compact = geometry.size.width < 680
            HStack(spacing: 0) {
                if !compact {
                    sessionsPanel.frame(width: 220)
                    Divider()
                }
                conversationPane(compact: compact)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(appState.themeBg)
        .featureGuideOnFirstVisit(.assistant)
        .task { await open() }
        .onChange(of: appState.pendingAssistantEmailContext?.id) { _, _ in
            if acceptsEmailHandoff { Task { await takeEmails() } }
        }
        .onChange(of: appState.pendingAssistantSalesContext?.id) { _, _ in
            if acceptsEmailHandoff { Task { await takeSales() } }
        }
        .onChange(of: appState.pendingAssistantJobContext?.id) { _, _ in
            if acceptsEmailHandoff { Task { await takeJob() } }
        }
        .onChange(of: appState.pendingAssistantTaskContext?.id) { _, _ in
            if acceptsEmailHandoff { Task { await takeTask() } }
        }
        .sheet(isPresented: $showAbilities) {
            AssistantAbilitiesSheet().environment(appState)
        }
        .sheet(isPresented: $showEditor) {
            VStack(alignment: .leading, spacing: 12) {
                Text(editing == nil ? "New session" : "Rename session").font(.headline)
                TextField("Name", text: $title).textFieldStyle(.roundedBorder)
                if let errorMessage { Text(errorMessage).foregroundColor(.orange).font(.caption) }
                HStack {
                    Spacer()
                    Button("Cancel") { showEditor = false }.keyboardShortcut(.cancelAction)
                    Button("Save") { Task { await saveConversation() } }
                        .keyboardShortcut(.defaultAction)
                        .disabled(loading || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || title.count > 100)
                }
            }.padding(16).frame(width: 360)
        }
    }

    private func conversationPane(compact: Bool) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                if compact {
                    Button { showSessionPicker.toggle() } label: {
                        Label("Sessions", systemImage: "sidebar.left")
                    }
                    .popover(isPresented: $showSessionPicker, arrowEdge: .bottom) {
                        sessionsPanel.frame(width: 260, height: 430).environment(appState)
                    }
                } else {
                    Text(conversations.first { $0.id == channelId }?.title ?? "Espresso")
                        .font(.system(size: 12, weight: .semibold)).lineLimit(1)
                }
                Spacer(minLength: 4)
                Button("Rename") {
                    if let item = conversations.first(where: { $0.id == channelId }) { editSession(item) }
                }
                .disabled(channelId == nil || loading)
                Button(action: newSession) {
                    Image(systemName: "square.and.pencil")
                }
                .help("New session").accessibilityLabel("New session")
                .disabled(loading)
            }
            .controlSize(.small)
            .padding(10)
            Divider()
            if let errorMessage {
                HStack {
                    Text(errorMessage).font(.system(size: 11)).foregroundColor(.orange)
                    Spacer()
                    Button("Try again") { Task { await open() } }.controlSize(.small)
                }.padding(10)
            }
            if let channelId {
                ChannelDetailView(
                    channelId: channelId, isEmbedded: true, isAssistant: true,
                    onOpenAbilities: { showAbilities = true }, initialDraft: initialDraft
                )
                .id(channelId) // a switch must reset composer, replies, attachments and socket VM
            } else {
                ProgressView().controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private var sessionsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Sessions").font(.system(size: 13, weight: .semibold))
            Button(action: newSession) { Label("New session", systemImage: "plus") }
                .buttonStyle(.borderedProminent).tint(appState.themeAccent)
                .disabled(loading)
            TextField("Filter sessions", text: $sessionSearch)
                .textFieldStyle(.roundedBorder).controlSize(.small)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 3) {
                    ForEach(visibleSessions) { item in
                        Button { select(item.id) } label: {
                            HStack(spacing: 7) {
                                Image(systemName: "bubble.left.and.bubble.right")
                                Text(item.title).lineLimit(2).multilineTextAlignment(.leading)
                                Spacer(minLength: 0)
                                if item.id == channelId { Image(systemName: "checkmark").font(.system(size: 9)) }
                            }
                            .font(.system(size: 11))
                            .foregroundColor(item.id == channelId ? appState.themeAccent : appState.themeTextSecondary)
                            .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                            .background(item.id == channelId ? appState.themeAccent.opacity(0.09) : .clear,
                                        in: RoundedRectangle(cornerRadius: 6))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button("Rename session") { editSession(item) }.disabled(loading)
                        }
                    }
                    if loading && conversations.isEmpty { ProgressView().controlSize(.small).padding(8) }
                    if !loading && visibleSessions.isEmpty {
                        Text(sessionSearch.isEmpty ? "No sessions yet" : "No matching sessions")
                            .font(.system(size: 11)).foregroundColor(appState.themeTextSecondary).padding(8)
                    }
                    if hasMore {
                        Button("Load older sessions") { Task { await loadMore() } }
                            .font(.system(size: 11)).disabled(loading).padding(8)
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(appState.themeSidebar)
    }

    private var visibleSessions: [AssistantConversation] {
        let query = sessionSearch.trimmingCharacters(in: .whitespacesAndNewlines)
        return query.isEmpty ? conversations : conversations.filter { $0.title.localizedCaseInsensitiveContains(query) }
    }

    private func newSession() {
        editing = nil
        title = "New session"
        createKey = UUID()
        showSessionPicker = false
        showEditor = true
    }

    private func editSession(_ item: AssistantConversation) {
        editing = item
        title = item.title
        showSessionPicker = false
        showEditor = true
    }

    private func select(_ id: String, draft: String = "") {
        initialDraft = draft
        channelId = id
        sessionSearch = ""
        showSessionPicker = false
        UserDefaults.standard.set(id, forKey: selectionKey)
    }

    private func open() async {
        await operations.run {
            errorMessage = nil
            do {
                let fallback = try await MatchaWorkService.shared.ensureAssistantChannel()
                try await reload()
                if channelId == nil {
                    let saved = UserDefaults.standard.string(forKey: selectionKey)
                    select(conversations.first { $0.id == saved }?.id ?? conversations.first?.id ?? fallback)
                }
            } catch { report(error) }
            // Queued while loading, then drained when opening finishes.
            if acceptsEmailHandoff { await takeEmails(); await takeSales(); await takeJob(); await takeTask() }
        }
    }

    private func reload() async throws {
        let response = try await MatchaWorkService.shared.assistantConversations()
        conversations = response.conversations
        hasMore = response.hasMore
    }

    private func loadMore() async {
        await operations.run {
            do {
                let response = try await MatchaWorkService.shared.assistantConversations(offset: conversations.count)
                let ids = Set(conversations.map(\.id))
                conversations.append(contentsOf: response.conversations.filter { !ids.contains($0.id) })
                hasMore = response.hasMore
            } catch { report(error) }
        }
    }

    private func saveConversation() async {
        await operations.run {
            do {
                let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
                if let editing {
                    try await MatchaWorkService.shared.renameAssistantConversation(id: editing.id, title: name)
                } else {
                    let id = try await MatchaWorkService.shared.createAssistantConversation(title: name, requestId: createKey)
                    select(id)
                }
                try await reload()
                showEditor = false
                errorMessage = nil
            } catch { report(error) }
        }
    }

    private func takeEmails() async {
        await operations.take(
            pending: { appState.pendingAssistantEmailContext },
            create: { request in
                let id = try await MatchaWorkService.shared.createAssistantConversation(
                    title: request.emails.count == 1 ? "Email conversation" : "\(request.emails.count) emails",
                    requestId: request.id)
                try await reload()
                return id
            },
            select: { select($0, draft: $1) },
            consume: { id in
                if appState.pendingAssistantEmailContext?.id == id {
                    appState.pendingAssistantEmailContext = nil
                }
            },
            report: report
        )
    }

    private func takeSales() async {
        await operations.take(
            pending: { () -> AssistantSalesContext? in
                guard let request = appState.pendingAssistantSalesContext,
                      request.owner == appState.currentUser?.id else { return nil }
                return request
            },
            create: { (request: AssistantSalesContext) in
                let id = try await MatchaWorkService.shared.createAssistantConversation(
                    title: String("Sales: \(request.title)".prefix(100)), requestId: request.id)
                try await reload()
                return id
            },
            select: { select($0, draft: $1) },
            consume: { id in
                if appState.pendingAssistantSalesContext?.id == id { appState.pendingAssistantSalesContext = nil }
            }, report: report)
    }

    private func takeJob() async {
        await operations.take(
            pending: { () -> AssistantJobContext? in
                guard let request = appState.pendingAssistantJobContext,
                      request.owner == appState.currentUser?.id else { return nil }
                return request
            },
            create: { (request: AssistantJobContext) in
                let id = try await MatchaWorkService.shared.createAssistantConversation(
                    title: request.conversationTitle, requestId: request.id)
                try await reload()
                return id
            },
            select: { select($0, draft: $1) },
            consume: { id in
                if appState.pendingAssistantJobContext?.id == id { appState.pendingAssistantJobContext = nil }
            }, report: report)
    }

    private func takeTask() async {
        await operations.take(
            pending: { () -> AssistantTaskContext? in
                guard let request = appState.pendingAssistantTaskContext,
                      request.owner == appState.currentUser?.id else { return nil }
                return request
            },
            create: { (request: AssistantTaskContext) in
                let id = try await MatchaWorkService.shared.createAssistantConversation(
                    title: request.conversationTitle, requestId: request.id)
                try await reload()
                return id
            },
            select: { select($0, draft: $1) },
            consume: { id in
                if appState.pendingAssistantTaskContext?.id == id { appState.pendingAssistantTaskContext = nil }
            }, report: report)
    }

    private func report(_ error: Error) {
        if let error = error as? APIError {
            if let plan = error.planRequirement { appState.presentPaywall(for: plan.feature) }
            errorMessage = AssistantText.message(for: error)
        } else { errorMessage = "Couldn't open your conversation with Espresso." }
    }
}

enum AssistantText {
    /// What the server said went wrong, as one line. FastAPI puts it in
    /// `detail`, either as a string or as `{ message }`.
    static func message(for error: APIError, fallback: String = "Something went wrong. Please try again.") -> String {
        guard case let .httpError(_, body) = error,
              let data = body.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return fallback
        }
        if let detail = json["detail"] as? String, !detail.isEmpty { return detail }
        if let detail = json["detail"] as? [String: Any],
           let text = detail["message"] as? String, !text.isEmpty {
            return text
        }
        return fallback
    }
}

/// What Espresso may do for this person. Looking things up is always on. An
/// ability that acts (send, invite, book) is switched on here, after the
/// person has read what it does with their data.
struct AssistantAbilitiesSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var data: AssistantAbilities?
    @State private var errorMessage: String?
    @State private var busyKey: String?
    @State private var consenting: AssistantAbility?
    @State private var showCalendars = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("What Espresso can do")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
            .padding(14)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if data?.isDryRun == true {
                        Label("Some actions are in preview mode. Each ability below shows whether its changes are live.",
                              systemImage: "exclamationmark.triangle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let errorMessage {
                        Text(errorMessage)
                            .font(.system(size: 11))
                            .foregroundColor(.red)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if data == nil && errorMessage == nil {
                        ProgressView().controlSize(.small)
                    }
                    ForEach(data?.abilities ?? []) { ability in
                        row(ability)
                    }
                }
                .padding(14)
            }
        }
        .frame(width: 440, height: 480)
        .task { await load() }
        .onChange(of: appState.foregroundTick) {
            // Back from Google's consent in the browser: read the list again.
            Task { await load() }
        }
        .sheet(isPresented: $showCalendars) {
            VStack {
                HStack { Text("Calendars").font(.headline); Spacer(); Button("Done") { showCalendars = false } }.padding()
                CalendarConnectionsView()
            }.frame(width: 520, height: 560).environment(appState)
        }
        .sheet(item: $consenting) { ability in
            AssistantConsentSheet(ability: ability) { contact in
                await accept(ability, contact: contact)
            }
            .environment(appState)
        }
    }

    @ViewBuilder
    private func row(_ ability: AssistantAbility) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(ability.label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
                if ability.alwaysOn {
                    Text("Always on").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                } else if ability.enabled {
                    Button("Switch off") { Task { await switchOff(ability) } }
                        .buttonStyle(.plain)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(appState.themeTextSecondary)
                        .disabled(busyKey == ability.key)
                } else {
                    Button(ability.consentOutdated ? "Review and switch on" : "Switch on") {
                        consenting = ability
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                    .controlSize(.small)
                    .disabled(busyKey == ability.key)
                }
            }
            Label(ability.key == "sales" ? "Builds pipelines and drafts; you review before sending" : ability.key == "jobs" ? "Reads your job searches and keeps your notes; never applies" : (ability.acts ? "Acts for you, only in this private conversation" : "Looks things up"),
                  systemImage: ability.acts ? "lock.fill" : "magnifyingglass")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
            if ability.enabled && ability.acts {
                Text((ability.commitMode ?? data?.commitMode) == "live" ? "Changes are live" : "Changes are previewed only")
                    .font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
            }
            if ability.key == "calendar" {
                Button("Connect and manage calendars…") { showCalendars = true }
                    .controlSize(.small)
            }
            if ability.enabled && ability.available && (!ability.needsConnection || ability.key == "calendar") {
                Label("Ready", systemImage: "checkmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.green)
            }
            if ability.enabled, ability.key != "calendar", let reason = ability.reason {
                Text(reason)
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if ability.enabled && ability.needsConnection && ability.key != "calendar" {
                Button(data?.google.connected == true ? "Reconnect Google" : "Connect Google") {
                    Task { await connect(ability) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(busyKey == ability.key)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(appState.themeBorder, lineWidth: 1)
        )
    }

    private func load() async {
        do {
            data = try await MatchaWorkService.shared.assistantAbilities()
            errorMessage = nil
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Couldn't load what Espresso can do."
        }
    }

    /// Returns what went wrong, or nil when the ability is now on.
    private func accept(_ ability: AssistantAbility, contact: AssistantContact?) async -> String? {
        busyKey = ability.key
        defer { busyKey = nil }
        do {
            try await MatchaWorkService.shared.enableAssistantAbility(
                ability.key, consentVersion: ability.disclosure?.version, contact: contact
            )
            consenting = nil
            await load()
            return nil
        } catch let error as APIError {
            return AssistantText.message(for: error)
        } catch {
            return "Something went wrong. Please try again."
        }
    }

    private func switchOff(_ ability: AssistantAbility) async {
        busyKey = ability.key
        defer { busyKey = nil }
        do {
            try await MatchaWorkService.shared.disableAssistantAbility(ability.key)
            await load()
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Something went wrong. Please try again."
        }
    }

    private func connect(_ ability: AssistantAbility) async {
        busyKey = ability.key
        defer { busyKey = nil }
        do {
            let raw = try await MatchaWorkService.shared.connectGoogle(forAbility: ability.key)
            // Google's own consent page, and nothing else, is opened.
            guard let url = URL(string: raw), url.scheme == "https",
                  url.host() == "accounts.google.com" else {
                errorMessage = "Couldn't start Google's sign-in."
                return
            }
            NSWorkspace.shared.open(url)
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Something went wrong. Please try again."
        }
    }
}

/// The disclosure for one ability. Nothing is switched on until it is accepted.
struct AssistantConsentSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    let ability: AssistantAbility
    /// Switches the ability on; returns what went wrong, or nil.
    let onAccept: (AssistantContact?) async -> String?

    @State private var contact = AssistantContact(name: "", phone: "", email: "")
    @State private var errorMessage: String?
    @State private var working = false

    private var needsContact: Bool { ability.key == "reservations" }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(ability.disclosure?.title ?? ability.label)
                .font(.system(size: 14, weight: .semibold))
            ForEach(ability.disclosure?.body ?? [], id: \.self) { line in
                Text(line)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if needsContact {
                Divider()
                Text("Book under").font(.system(size: 11, weight: .semibold))
                TextField("Full name", text: $contact.name)
                TextField("Phone", text: $contact.phone)
                TextField("Email", text: $contact.email)
            }
            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Spacer()
                Button("Not now") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button {
                    Task {
                        working = true
                        errorMessage = await onAccept(needsContact ? contact : nil)
                        working = false
                    }
                } label: {
                    Text("I understand, switch it on")
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(working || (needsContact && !contact.isUsable))
            }
        }
        .textFieldStyle(.roundedBorder)
        .padding(16)
        .frame(width: 420)
        .onAppear {
            if let saved = ability.contact { contact = saved }
        }
    }
}
