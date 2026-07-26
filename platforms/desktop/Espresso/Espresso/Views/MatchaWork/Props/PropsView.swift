import SwiftUI

/// The "Props" tab: a list of proposal drafts (Feat/Fix) that collaborators
/// shape by chatting with the repo, then promote to real kanban tickets.
struct PropsView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var drafts: [MWTicketDraft] = []
    @State private var selected: MWTicketDraft?
    @State private var loading = false

    private var projectId: String? { viewModel.project?.id }

    var body: some View {
        VStack(spacing: 0) {
            if let d = selected {
                PropDetailView(
                    viewModel: viewModel,
                    draft: d,
                    onBack: { selected = nil; Task { await reload() } },
                    onChanged: { updated in
                        if let i = drafts.firstIndex(where: { $0.id == updated.id }) { drafts[i] = updated }
                        selected = updated
                    }
                )
            } else {
                header
                Divider().opacity(0.2)
                list
            }
        }
        .background(Color.appBackground)
        .task {
            if viewModel.elements.isEmpty { await viewModel.loadElements() }
            await reload()
            // Freshen the code snapshot on open — gated (cooldown + no-concurrent
            // + needs-globs) so repeated tab opens never spam GitHub.
            await viewModel.autoSyncFromGitHubIfStale()
        }
    }

    private var header: some View {
        HStack(spacing: 6) {
            Image(systemName: "lightbulb").font(.system(size: 10)).foregroundColor(.secondary)
            Text("Chat with the repo to shape a Feat or Fix, then promote to a ticket.")
                .font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
            Spacer()
            Button { create(kind: "feat") } label: {
                pill(icon: "sparkles", text: "New Feat", color: .teal)
            }.buttonStyle(.plain)
            Button { create(kind: "fix") } label: {
                pill(icon: "wrench.and.screwdriver", text: "New Fix", color: .orange)
            }.buttonStyle(.plain)
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
    }

    private func pill(icon: String, text: String, color: Color) -> some View {
        HStack(spacing: 3) { Image(systemName: icon); Text(text) }
            .font(.system(size: 10, weight: .medium)).foregroundColor(color)
            .padding(.horizontal, 6).padding(.vertical, 3)
            .background(color.opacity(0.12)).cornerRadius(4)
    }

    private var list: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                if drafts.isEmpty && !loading {
                    Text("No proposals yet. Start a Feat or Fix to brainstorm with the repo.")
                        .font(.system(size: 11)).foregroundColor(.secondary)
                        .multilineTextAlignment(.center).padding(.top, 28).padding(.horizontal, 24)
                        .frame(maxWidth: .infinity)
                }
                ForEach(drafts) { d in row(d) }
            }
            .padding(10)
        }
    }

    private func row(_ d: MWTicketDraft) -> some View {
        HStack(spacing: 8) {
            Image(systemName: d.isFeat ? "sparkles" : "wrench.and.screwdriver")
                .font(.system(size: 12)).foregroundColor(d.isFeat ? .teal : .orange)
            VStack(alignment: .leading, spacing: 1) {
                Text((d.title?.isEmpty == false ? d.title! : "Untitled \(d.isFeat ? "feature" : "fix")"))
                    .font(.system(size: 12, weight: .medium)).foregroundColor(.white).lineLimit(1)
                if let el = elementName(d.elementId) {
                    Text(el).font(.system(size: 9)).foregroundColor(.secondary).lineLimit(1)
                }
            }
            Spacer()
            if d.status == "promoted" {
                Text("Promoted").font(.system(size: 9)).foregroundColor(.green)
            }
            Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold))
                .foregroundColor(.secondary.opacity(0.4))
        }
        .padding(.horizontal, 8).padding(.vertical, 7)
        .background(Color.zinc900.opacity(0.4)).cornerRadius(5)
        .contentShape(Rectangle())
        .onTapGesture { selected = d }
    }

    private func elementName(_ id: String?) -> String? {
        guard let id else { return nil }
        return viewModel.elements.first(where: { $0.id == id })?.name
    }

    private func create(kind: String) {
        guard let pid = projectId else { return }
        Task {
            do {
                let d = try await MatchaWorkService.shared.createTicketDraft(projectId: pid, kind: kind)
                await MainActor.run { drafts.insert(d, at: 0); selected = d }
            } catch {
                await MainActor.run { viewModel.errorMessage = error.localizedDescription }
            }
        }
    }

    private func reload() async {
        guard let pid = projectId else { return }
        await MainActor.run { loading = true }
        do {
            let list = try await MatchaWorkService.shared.listTicketDrafts(projectId: pid)
            await MainActor.run { drafts = list; loading = false }
        } catch {
            await MainActor.run { loading = false }
        }
    }
}

/// One Prop: repo-grounded chat (top) + a draft panel (title/element/subtasks)
/// with Generate-draft and Promote-to-ticket.
struct PropDetailView: View {
    let viewModel: ProjectDetailViewModel
    let draft: MWTicketDraft
    let onBack: () -> Void
    let onChanged: (MWTicketDraft) -> Void

    @State private var working: MWTicketDraft
    @State private var messages: [MWPropMessage] = []
    @State private var input = ""
    @State private var sending = false
    @State private var generating = false
    @State private var showPromote = false

    private var projectId: String? { viewModel.project?.id }

    init(viewModel: ProjectDetailViewModel, draft: MWTicketDraft,
         onBack: @escaping () -> Void, onChanged: @escaping (MWTicketDraft) -> Void) {
        self.viewModel = viewModel
        self.draft = draft
        self.onBack = onBack
        self.onChanged = onChanged
        _working = State(initialValue: draft)
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.2)
            chat
            Divider().opacity(0.2)
            draftPanel
            inputBar
        }
        .background(Color.appBackground)
        .task { await loadMessages() }
        .sheet(isPresented: $showPromote) { promoteSheet }
    }

    // MARK: header

    private var header: some View {
        HStack(spacing: 6) {
            Button(action: onBack) {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left").font(.system(size: 9, weight: .semibold))
                    Text("Props")
                }
                .font(.system(size: 10)).foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            Text("·").font(.system(size: 10)).foregroundColor(.secondary.opacity(0.5))
            Image(systemName: working.isFeat ? "sparkles" : "wrench.and.screwdriver")
                .font(.system(size: 11)).foregroundColor(working.isFeat ? .teal : .orange)
            Text(working.isFeat ? "Feature" : "Fix")
                .font(.system(size: 11, weight: .semibold)).foregroundColor(.white)
            if working.status == "promoted" {
                Text("Promoted").font(.system(size: 9)).foregroundColor(.green)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Color.green.opacity(0.15)).cornerRadius(3)
            }
            Spacer()
            elementMenu
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
    }

    private var elementMenu: some View {
        Menu {
            Button("No grounding") { setElement(nil) }
            ForEach(viewModel.elements.filter { $0.hasRepoBinding }) { el in
                Button(el.name) { setElement(el.id) }
            }
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "chevron.left.forwardslash.chevron.right").font(.system(size: 9))
                Text(viewModel.elements.first(where: { $0.id == working.elementId })?.name ?? "Pick code element")
                    .lineLimit(1)
            }
            .font(.system(size: 10)).foregroundColor(.matcha500)
        }
        .menuStyle(.borderlessButton).fixedSize()
    }

    // MARK: chat

    private var chat: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                if messages.isEmpty {
                    Text("Ask the repo anything — e.g. “where would a dark-mode toggle live?” The AI answers from \(elementLabel).")
                        .font(.system(size: 11)).foregroundColor(.secondary)
                        .padding(.top, 16).frame(maxWidth: .infinity)
                }
                ForEach(messages) { m in messageRow(m) }
                if sending {
                    HStack(spacing: 5) {
                        ProgressView().controlSize(.small)
                        Text("Thinking…").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                }
            }
            .padding(12)
        }
        .frame(maxHeight: .infinity)
    }

    private var elementLabel: String {
        viewModel.elements.first(where: { $0.id == working.elementId }).map { "“\($0.name)”" } ?? "the synced code"
    }

    private func messageRow(_ m: MWPropMessage) -> some View {
        let isUser = m.role == "user"
        return HStack {
            if isUser { Spacer(minLength: 40) }
            Text(m.content)
                .font(.system(size: 12)).foregroundColor(isUser ? .white : .white.opacity(0.92))
                .textSelection(.enabled)
                .padding(.horizontal, 9).padding(.vertical, 6)
                .background(isUser ? Color.matcha500.opacity(0.25) : Color.zinc800.opacity(0.7))
                .cornerRadius(7)
            if !isUser { Spacer(minLength: 40) }
        }
    }

    // MARK: draft panel

    private var draftPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                TextField("Working title…", text: Binding(
                    get: { working.title ?? "" },
                    set: { working.title = $0.isEmpty ? nil : $0 }
                ))
                .textFieldStyle(.plain).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                .onSubmit { Task { await persist(.init(title: working.title)) } }
                Spacer()
                Button { Task { await generate() } } label: {
                    HStack(spacing: 3) {
                        if generating { ProgressView().controlSize(.small) }
                        else { Image(systemName: "wand.and.stars") }
                        Text("Generate draft")
                    }
                    .font(.system(size: 10, weight: .medium)).foregroundColor(.matcha500)
                }
                .buttonStyle(.plain).disabled(generating)
                Button { showPromote = true } label: {
                    Text("Promote").font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Color.matcha500).cornerRadius(4)
                }
                .buttonStyle(.plain)
                .disabled((working.title ?? "").isEmpty)
            }
            if let subs = working.draftSubtasks, !subs.isEmpty {
                ForEach(Array(subs.enumerated()), id: \.offset) { _, s in
                    HStack(spacing: 5) {
                        Image(systemName: "circle").font(.system(size: 7)).foregroundColor(.secondary)
                        Text(s).font(.system(size: 11)).foregroundColor(.white.opacity(0.85)).lineLimit(1)
                    }
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(Color.zinc900.opacity(0.5))
    }

    // MARK: input

    private var inputBar: some View {
        HStack(spacing: 6) {
            TextField("Message the repo…", text: $input, axis: .vertical)
                .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white)
                .lineLimit(1...4)
                .padding(7).background(Color.zinc800.opacity(0.6)).cornerRadius(6)
                .onSubmit { send() }
            Button { send() } label: {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 20))
                    .foregroundColor(canSend ? .matcha500 : .secondary.opacity(0.4))
            }
            .buttonStyle(.plain).disabled(!canSend)
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
    }

    private var canSend: Bool { !sending && !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    // MARK: promote sheet

    private var promoteSheet: some View {
        let seed = MWTaskDraft(
            title: working.title ?? "",
            description: working.description,
            priority: working.priority,
            category: working.kind,
            boardColumn: "todo",
            assignedTo: nil,
            assignedName: nil,
            elementId: working.elementId,
            elementName: viewModel.elements.first(where: { $0.id == working.elementId })?.name,
            subtasks: working.draftSubtasks
        )
        return AIDraftReviewSheet(
            draft: seed,
            collaborators: viewModel.collaborators,
            elements: viewModel.elements,
            onCreate: { title, column, priority, assignedTo, description, category, elementId, subtasks in
                await promote(title: title, column: column, priority: priority, assignedTo: assignedTo,
                              description: description, category: category, elementId: elementId, subtasks: subtasks)
            },
            onClose: { showPromote = false }
        )
    }

    // MARK: actions

    private func loadMessages() async {
        guard let pid = projectId else { return }
        if let list = try? await MatchaWorkService.shared.listPropMessages(projectId: pid, draftId: draft.id) {
            await MainActor.run { messages = list }
        }
    }

    private func send() {
        guard canSend, let pid = projectId else { return }
        let content = input.trimmingCharacters(in: .whitespacesAndNewlines)
        input = ""
        sending = true
        Task {
            do {
                let turn = try await MatchaWorkService.shared.postPropMessage(projectId: pid, draftId: draft.id, content: content)
                await MainActor.run {
                    messages.append(turn.userMessage)
                    messages.append(turn.assistantMessage)
                    sending = false
                }
            } catch {
                await MainActor.run { sending = false; viewModel.errorMessage = error.localizedDescription }
            }
        }
    }

    private func generate() async {
        guard let pid = projectId else { return }
        await MainActor.run { generating = true }
        do {
            let updated = try await MatchaWorkService.shared.generateDraftFields(projectId: pid, draftId: draft.id)
            await MainActor.run { working = updated; onChanged(updated); generating = false }
        } catch {
            await MainActor.run { generating = false; viewModel.errorMessage = error.localizedDescription }
        }
    }

    private func setElement(_ id: String?) {
        working.elementId = id
        Task { await persist(.init(element_id: id ?? "")) }
    }

    private func persist(_ patch: MatchaWorkService.TicketDraftPatch) async {
        guard let pid = projectId else { return }
        do {
            let updated = try await MatchaWorkService.shared.updateTicketDraft(projectId: pid, draftId: draft.id, patch: patch)
            await MainActor.run { working = updated; onChanged(updated) }
        } catch {
            await MainActor.run { viewModel.errorMessage = error.localizedDescription }
        }
    }

    private func promote(title: String, column: String, priority: String, assignedTo: String?,
                         description: String?, category: String, elementId: String?, subtasks: [String]?) async {
        guard let pid = projectId else { return }
        let overrides = MatchaWorkService.PromoteOverrides(
            title: title, description: description, priority: priority, category: category,
            board_column: column, element_id: elementId, assigned_to: assignedTo, subtasks: subtasks
        )
        do {
            _ = try await MatchaWorkService.shared.promoteDraft(projectId: pid, draftId: draft.id, overrides: overrides)
            await viewModel.loadTasks()
            await MainActor.run {
                working.status = "promoted"
                onChanged(working)
                showPromote = false
            }
        } catch {
            await MainActor.run { viewModel.errorMessage = error.localizedDescription }
        }
    }
}
