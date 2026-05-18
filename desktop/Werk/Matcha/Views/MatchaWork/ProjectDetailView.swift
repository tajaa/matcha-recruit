import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ProjectDetailView: View {
    let projectId: String
    @Environment(AppState.self) private var appState
    @State private var viewModel = ProjectDetailViewModel()
    @State private var chatVM = ThreadDetailViewModel()
    @State private var presenceVM = ProjectPresenceViewModel()
    @State private var editingSectionId: String?
    @State private var newSectionTitle = ""
    @State private var showCollaborators = false
    @State private var showExportMenu = false
    @State private var collabPanel: CollabRightPanel = .chat
    @State private var showCompleteConfirm = false
    @State private var showRenameAlert = false
    @State private var renameDraft = ""
    @State private var standardMode: StandardProjectMode = .edit
    @State private var collabDiscussionChannelId: String?
    @State private var collabChannelLoadError: String?
    // Cancelable task handles so rapid project/thread switches don't queue
    // up redundant fetches.
    @State private var threadLoadTask: Task<Void, Never>?
    @State private var refreshTask: Task<Void, Never>?
    @State private var ensureChannelTask: Task<Void, Never>?
    @AppStorage("mw-chat-theme") private var lightMode = false
    @AppStorage("mw-model") private var selectedModelId = "flash"

    /// True for general-shaped projects that use `standardLayout` (sections +
    /// chat). Used to gate the Edit/Preview tab toggle in the toolbar so it
    /// doesn't show on recruiting / blog (which already has its own preview tab) /
    /// collab / discipline.
    private var isStandardLayout: Bool {
        let t = viewModel.project?.projectType ?? ""
        return !["recruiting", "blog", "collab", "discipline"].contains(t)
    }

    private var selectedModelValue: String? {
        mwModelOptions.first { $0.id == selectedModelId }?.value
    }

    var body: some View {
        Group {
            if viewModel.project?.projectType == "recruiting" {
                recruitingLayout
            } else if viewModel.project?.projectType == "blog" {
                BlogEditorView(
                    viewModel: viewModel,
                    chatVM: chatVM,
                    lightMode: lightMode,
                    selectedModel: selectedModelValue
                )
            } else if viewModel.project?.projectType == "collab" {
                collabLayout
            } else if viewModel.project?.projectType == "discipline" {
                VStack(spacing: 0) {
                    DisciplineWorkflowBar(viewModel: viewModel)
                    standardLayout
                }
            } else {
                standardLayout
            }
        }
        .task(id: projectId) {
            // Single .task: wire realtime callbacks → connect/join WS →
            // then load the project. Sequencing matters: the previous
            // two-block layout relied on SwiftUI's "best effort" ordering
            // between adjacent .task modifiers, which sometimes raced the
            // first task.updated event into a window where callbacks
            // weren't attached yet. SwiftUI auto-cancels this block when
            // projectId changes.
            viewModel.attachTaskRealtime(currentUserId: appState.currentUser?.id)
            presenceVM.start(projectId: projectId, pageKey: collabPanel.rawValue)
            await viewModel.loadProject(id: projectId)
        }
        .onChange(of: collabPanel) { _, newPanel in
            presenceVM.setPage(newPanel.rawValue)
        }
        .onDisappear {
            presenceVM.stop()
        }
        .onChange(of: viewModel.activeChatId) {
            threadLoadTask?.cancel()
            if let chatId = viewModel.activeChatId {
                threadLoadTask = Task { await chatVM.loadThread(id: chatId) }
            }
        }
        // Chat streams mutate project data (sections for blog, posting for
        // recruiting, etc.) via server-side directives.
        // Refetch the project when a stream completes so the panel reflects
        // the new state without requiring the user to navigate away and back.
        // Cancel any in-flight refresh so rapid stream-end events coalesce.
        .onReceive(NotificationCenter.default.publisher(for: .mwProjectDataChanged)) { _ in
            refreshTask?.cancel()
            refreshTask = Task { await viewModel.refreshProject() }
        }
        .toolbar {
            ToolbarItem(placement: .navigation) {
                if let project = viewModel.project {
                    Button {
                        renameDraft = project.title
                        showRenameAlert = true
                    } label: {
                        HStack(spacing: 4) {
                            // Lowercased eyebrow + title in one line replaces
                            // the loud all-caps "COLLAB" + bold title stack.
                            // Click anywhere on the row to rename.
                            if let type = project.projectType, !type.isEmpty {
                                Text(type.lowercased())
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.45))
                                Text("·")
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.3))
                            }
                            Text(project.title)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(.white)
                            Image(systemName: "pencil")
                                .font(.system(size: 9))
                                .foregroundColor(.white.opacity(0.4))
                        }
                    }
                    .buttonStyle(.plain)
                    .help("Click to rename")
                }
            }
            ToolbarItemGroup(placement: .principal) {
                if isStandardLayout {
                    Picker("Mode", selection: $standardMode) {
                        ForEach(StandardProjectMode.allCases) { mode in
                            Text(mode.label).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 160)
                }
            }
            ToolbarItemGroup(placement: .primaryAction) {
                // Per-panel quick action for collab projects so users don't
                // hunt for "add" inside each tab. Swaps with the active panel.
                if viewModel.project?.projectType == "collab" {
                    collabPanelAction
                }
                Menu {
                    ForEach(mwModelOptions) { option in
                        Button {
                            selectedModelId = option.id
                        } label: {
                            HStack {
                                Text(option.label)
                                if selectedModelId == option.id {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 3) {
                        Image(systemName: "cpu")
                            .font(.system(size: 10))
                        Text(mwModelOptions.first { $0.id == selectedModelId }?.label ?? "Flash")
                            .font(.system(size: 10, weight: .medium))
                    }
                    .padding(.horizontal, 7)
                    .padding(.vertical, 4)
                    .background(Color.zinc800)
                    .cornerRadius(6)
                    .foregroundColor(.secondary)
                }
                .menuStyle(.borderlessButton)

                // Live presence pill — small avatar dots for everyone in the
                // project right now. Pulses softly so it reads as live state
                // and not just "list of members". Click → opens the same
                // CollaboratorPanelView popover the static button used.
                if !presenceVM.members.isEmpty {
                    Button { showCollaborators = true } label: {
                        PresencePillContent(members: presenceVM.members)
                    }
                    .buttonStyle(.plain)
                    .help("Collaborators online now")
                    .popover(isPresented: $showCollaborators, arrowEdge: .bottom) {
                        if let pid = viewModel.project?.id {
                            CollaboratorPanelView(projectId: pid)
                                .frame(width: 300, height: 360)
                        }
                    }
                } else {
                    Button { showCollaborators = true } label: {
                        Image(systemName: "person.2").font(.system(size: 13))
                    }
                    .help("Collaborators")
                    .popover(isPresented: $showCollaborators) {
                        if let pid = viewModel.project?.id {
                            CollaboratorPanelView(projectId: pid)
                                .frame(width: 300, height: 360)
                        }
                    }
                }

                if viewModel.project?.projectType == "collab",
                   let pid = viewModel.project?.id {
                    Button {
                        appState.collabProjectWizardMode = .manage(projectId: pid)
                        appState.showCollabProjectWizard = true
                    } label: {
                        Image(systemName: "questionmark.circle").font(.system(size: 13))
                    }
                    .help("Collab project guide")
                }

                if viewModel.project?.projectType == "collab" {
                    if viewModel.project?.status == "completed" {
                        HStack(spacing: 3) {
                            Image(systemName: "checkmark.seal.fill")
                                .font(.system(size: 11))
                            Text("Completed")
                                .font(.system(size: 10, weight: .medium))
                        }
                        .foregroundColor(.matcha500)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 4)
                        .background(Color.matcha500.opacity(0.12))
                        .cornerRadius(6)
                    } else {
                        Button { showCompleteConfirm = true } label: {
                            Image(systemName: "checkmark.circle").font(.system(size: 13))
                        }
                        .help("Mark project complete")
                        .confirmationDialog(
                            "Mark project complete?",
                            isPresented: $showCompleteConfirm,
                            titleVisibility: .visible
                        ) {
                            Button("Complete") {
                                Task { await viewModel.markProjectComplete() }
                            }
                            Button("Cancel", role: .cancel) {}
                        } message: {
                            Text("Owner only. Project will move to the Completed section.")
                        }
                    }
                }

                Menu {
                    Button("PDF") { export(format: "pdf") }
                    Button("Markdown") { export(format: "md") }
                    Button("DOCX") { export(format: "docx") }
                } label: {
                    Image(systemName: "square.and.arrow.up").font(.system(size: 13))
                }
                .help("Export project")
            }
        }
        .alert("Rename project", isPresented: $showRenameAlert) {
            TextField("Project title", text: $renameDraft)
            Button("Save") {
                let trimmed = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmed.isEmpty else { return }
                Task { await viewModel.updateTitle(trimmed) }
            }
            Button("Cancel", role: .cancel) {}
        }
    }

    @ViewBuilder
    private var collabPanelAction: some View {
        switch collabPanel {
        case .sections:
            Button {
                Task { await viewModel.addSection(title: "New Section") }
            } label: {
                Image(systemName: "plus.rectangle").font(.system(size: 13))
            }
            .help("Add section")
        case .files:
            Button {
                NotificationCenter.default.post(name: .mwCollabFilesBrowse, object: nil)
            } label: {
                Image(systemName: "folder.badge.plus").font(.system(size: 13))
            }
            .help("Browse for files")
        case .kanban:
            Button {
                Task { await viewModel.loadTasks() }
            } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 13))
            }
            .help("Refresh tasks")
        default:
            EmptyView()
        }
    }

    private var collabTabStrip: some View {
        HStack(spacing: 2) {
            ForEach(CollabRightPanel.allCases) { panel in
                Button {
                    collabPanel = panel
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: panel.icon)
                            .font(.system(size: 11))
                        Text(panel.label)
                            .font(.system(size: 11, weight: .medium))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .foregroundColor(collabPanel == panel ? .white : .white.opacity(0.55))
                    .background(
                        RoundedRectangle(cornerRadius: 5)
                            .fill(collabPanel == panel ? Color.matcha600.opacity(0.25) : Color.clear)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 5)
                            .stroke(collabPanel == panel ? Color.matcha500.opacity(0.4) : Color.clear, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
                .keyboardShortcut(panel.shortcutKey, modifiers: .command)
            }
            Spacer()
            collabStatusPill
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }

    @ViewBuilder
    private var collabStatusPill: some View {
        let count = viewModel.project?.collaborators?.count ?? 0
        if count > 0 {
            HStack(spacing: 4) {
                Image(systemName: "person.2.fill")
                    .font(.system(size: 9))
                Text("\(count)")
                    .font(.system(size: 10, weight: .medium))
            }
            .foregroundColor(.white.opacity(0.55))
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(Color.zinc800.opacity(0.6))
            .cornerRadius(10)
        }
    }

    private var collabLayout: some View {
        VStack(spacing: 0) {
            collabTabStrip
            Divider().opacity(0.2)

            switch collabPanel {
            case .chat:
                collabChatView
            case .kanban:
                KanbanBoardView(viewModel: viewModel)
            case .files:
                ProjectFilesView(viewModel: viewModel)
            case .sections:
                collabSections
            case .overview:
                collabOverview
            }
        }
        .background(Color.appBackground)
        .onChange(of: viewModel.project?.id) { _, _ in
            // Lazy-create the per-project discussion channel. Cancel any
            // in-flight ensure call so rapid project switches don't stack
            // duplicate "Setting up the collab channel…" loaders.
            ensureChannelTask?.cancel()
            collabDiscussionChannelId = nil
            collabChannelLoadError = nil
            ensureChannelTask = Task { await ensureCollabDiscussionChannel() }
        }
        .task {
            ensureChannelTask?.cancel()
            ensureChannelTask = Task { await ensureCollabDiscussionChannel() }
        }
    }

    @ViewBuilder
    private var collabChatView: some View {
        if let channelId = collabDiscussionChannelId {
            ChannelDetailView(channelId: channelId)
        } else if let err = collabChannelLoadError {
            VStack(spacing: 12) {
                Spacer()
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 28))
                    .foregroundColor(.red)
                Text("Couldn't open collab chat")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white)
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                Button("Retry") {
                    collabChannelLoadError = nil
                    Task { await ensureCollabDiscussionChannel() }
                }
                .buttonStyle(.bordered)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.appBackground)
        } else {
            VStack(spacing: 10) {
                Spacer()
                ProgressView().tint(.secondary)
                Text("Setting up the collab channel…")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.appBackground)
        }
    }

    private func ensureCollabDiscussionChannel() async {
        guard let pid = viewModel.project?.id,
              viewModel.project?.projectType == "collab" else { return }
        if collabDiscussionChannelId != nil { return }
        do {
            let id = try await MatchaWorkService.shared.ensureProjectDiscussionChannel(projectId: pid)
            await MainActor.run { collabDiscussionChannelId = id }
        } catch {
            await MainActor.run { collabChannelLoadError = error.localizedDescription }
        }
    }

    @ViewBuilder
    private var chatLoadingView: some View {
        VStack(spacing: 12) {
            Spacer()
            if let err = viewModel.errorMessage {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 28))
                    .foregroundColor(.red)
                Text("Couldn't start chat")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white)
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                Button("Retry") {
                    Task {
                        viewModel.errorMessage = nil
                        await viewModel.createChat(title: nil)
                    }
                }
                .buttonStyle(.bordered)
            } else {
                ProgressView().tint(.secondary)
                Text("Starting chat…")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.appBackground)
    }

    private var collabSections: some View {
        // Wrap the panel in a presence overlay so remote cursor positions
        // render on top of the same coordinate space we report mouse moves
        // from. Page-scoped server-side, so cursor traffic only fans out
        // between users on the Sections sub-tab.
        ProjectPresenceOverlay(presenceVM: presenceVM, members: presenceVM.members) {
        VStack(spacing: 0) {
            if let sections = viewModel.project?.sections, !sections.isEmpty {
                if let sid = editingSectionId,
                   let section = sections.first(where: { $0.id == sid }) {
                    SectionEditorView(
                        section: section,
                        onSave: { title, content in
                            Task { await viewModel.updateSection(sectionId: sid, title: title, content: content) }
                        },
                        onCaretMove: { anchor, head in
                            presenceVM.reportCaret(sectionId: sid, anchor: anchor, head: head)
                        }
                    )
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(sections) { section in
                                let editingMember = remoteEditor(for: section.id)
                                Button { editingSectionId = section.id } label: {
                                    HStack(alignment: .top, spacing: 8) {
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text(section.title).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                                            if let c = section.content, !c.isEmpty {
                                                Text(c.prefix(120))
                                                    .font(.system(size: 10))
                                                    .foregroundColor(.secondary)
                                                    .lineLimit(2)
                                            }
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        if let m = editingMember {
                                            // Small colored dot + initial when a remote
                                            // collaborator's caret is in this section.
                                            // Skips in-text caret rendering for v1 — too
                                            // much NSTextView overlay work — but keeps
                                            // the at-a-glance "X is editing here" signal.
                                            HStack(spacing: 3) {
                                                Circle()
                                                    .fill(UserColor.forUserId(m.id))
                                                    .frame(width: 6, height: 6)
                                                Text(m.name).font(.system(size: 9)).foregroundColor(.secondary)
                                            }
                                        }
                                    }
                                    .padding(10)
                                    .background(Color.zinc900.opacity(0.5))
                                    .cornerRadius(6)
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 3)
                            }
                        }
                    }
                }
            } else {
                Spacer()
                Text("No sections yet — use the AI chat or click + to add.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            }
        }
        }
    }

    /// Returns the member whose caret is currently in the given section, if
    /// any. Used to render the "X is editing" badge on the section list.
    private func remoteEditor(for sectionId: String) -> ProjectWebSocket.PresenceMember? {
        guard let entry = presenceVM.remoteCarets.first(where: { $0.value.sectionId == sectionId }) else {
            return nil
        }
        return presenceVM.members.first { $0.id == entry.key }
    }

    private var collabOverview: some View {
        CollabOverviewView(
            viewModel: viewModel,
            collabPanel: $collabPanel,
            showCollaborators: $showCollaborators,
            onExport: { export(format: $0) }
        )
    }

    private var recruitingLayout: some View {
        HSplitView {
            // Left: Chat panel — drives the recruiting workflow
            if viewModel.activeChatId != nil {
                ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModelValue)
                    .frame(minWidth: 320)
            } else {
                VStack(spacing: 12) {
                    Spacer()
                    if let err = viewModel.errorMessage {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 28))
                            .foregroundColor(.red)
                        Text("Couldn't start chat")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.white)
                        Text(err)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 24)
                        Button("Retry") {
                            Task {
                                viewModel.errorMessage = nil
                                await viewModel.createChat(title: nil)
                            }
                        }
                        .buttonStyle(.bordered)
                    } else {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.system(size: 28))
                            .foregroundColor(.secondary)
                        Text("Starting chat…")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }
                .frame(minWidth: 320)
                .background(Color.appBackground)
                .task {
                    if viewModel.activeChatId == nil && viewModel.errorMessage == nil {
                        await viewModel.createChat(title: nil)
                    }
                }
            }

            // Right: Pipeline panel
            RecruitingPipelineView(viewModel: viewModel)
                .frame(minWidth: 300)
        }
        .background(Color.appBackground)
    }

    @ViewBuilder
    private var standardLayout: some View {
        if standardMode == .preview {
            MarkdownPreviewView(
                sections: viewModel.project?.sections ?? [],
                title: viewModel.project?.title ?? ""
            )
        } else {
            standardEditLayout
        }
    }

    private var standardEditLayout: some View {
        HSplitView {
            // Sidebar: Sections + Chats
            VStack(spacing: 0) {
                // Sections header
                HStack {
                    Text("Sections")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        Task { await viewModel.addSection(title: "New Section") }
                    } label: {
                        Image(systemName: "plus").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)

                if let sections = viewModel.project?.sections {
                    ForEach(sections) { section in
                        Button {
                            editingSectionId = section.id
                            viewModel.activeChatId = nil
                        } label: {
                            Text(section.title)
                                .font(.system(size: 12))
                                .foregroundColor(editingSectionId == section.id ? .white : .secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 5)
                                .background(editingSectionId == section.id ? Color.matcha600.opacity(0.2) : Color.clear)
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button("Delete", role: .destructive) {
                                Task { await viewModel.deleteSection(sectionId: section.id) }
                            }
                        }
                    }
                }

                Divider().opacity(0.3).padding(.vertical, 6)

                // Chats header
                HStack {
                    Text("Chats")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        Task { await viewModel.createChat(title: nil) }
                    } label: {
                        Image(systemName: "plus").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)

                // Chat list would come from project detail — for now show active chat
                if let chatId = viewModel.activeChatId {
                    Button {
                        editingSectionId = nil
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "bubble.left").font(.system(size: 10))
                            Text("Chat")
                                .font(.system(size: 12))
                        }
                        .foregroundColor(editingSectionId == nil ? .white : .secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(editingSectionId == nil ? Color.matcha600.opacity(0.2) : Color.clear)
                    }
                    .buttonStyle(.plain)
                }

                Spacer()
            }
            .frame(minWidth: 180, maxWidth: 220)
            .background(Color.appBackground)

            // Main content
            if let sectionId = editingSectionId,
               let section = viewModel.project?.sections?.first(where: { $0.id == sectionId }) {
                SectionEditorView(
                    section: section,
                    onSave: { title, content in
                        Task { await viewModel.updateSection(sectionId: sectionId, title: title, content: content) }
                    }
                )
            } else if viewModel.activeChatId != nil {
                ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModelValue)
            } else {
                ZStack {
                    Color.appBackground.ignoresSafeArea()
                    VStack(spacing: 12) {
                        Image(systemName: "folder").font(.system(size: 36)).foregroundColor(.secondary)
                        Text("Select a section or chat")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .background(Color.appBackground)
    }

    private func export(format: String) {
        let pid = viewModel.project?.id ?? "<nil>"
        print("[Export] start format=\(format) project=\(pid)")
        Task { @MainActor in
            let result = await viewModel.exportProject(format: format)
            print("[Export] response format=\(format) bytes=\(result?.count ?? -1) error=\(viewModel.errorMessage ?? "nil")")
            // Defer onto the next runloop tick so the menu/popover has finished
            // dismissing before we present the save panel or alert modal.
            DispatchQueue.main.async {
                guard let data = result, !data.isEmpty else {
                    let msg = viewModel.errorMessage ?? "Export returned no data."
                    print("[Export] \(format) failed: \(msg)")
                    let alert = NSAlert()
                    alert.messageText = "Export failed"
                    alert.informativeText = msg
                    alert.alertStyle = .warning
                    alert.runModal()
                    return
                }
                presentExportSavePanel(data: data, format: format, title: viewModel.project?.title ?? "project")
            }
        }
    }
}
