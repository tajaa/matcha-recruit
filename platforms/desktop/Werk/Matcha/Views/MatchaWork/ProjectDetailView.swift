import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ProjectDetailView: View {
    let projectId: String
    /// True when shown in a secondary (aux) window. Suppresses writes to the
    /// shared nav/tab context so it doesn't clobber the main window.
    var isEmbedded: Bool = false
    @Environment(AppState.self) var appState
    @State var viewModel = ProjectDetailViewModel()
    @State var chatVM = ThreadDetailViewModel()
    @State var presenceVM = ProjectPresenceViewModel()
    @State var editingSectionId: String?
    @State var emailingSection: MWProjectSection?
    @State var newSectionTitle = ""
    @State var showCollaborators = false
    @State var showExportMenu = false
    // Collab projects open on the Kanban board by default; deep-links (e.g. a
    // task notification setting pendingProjectPanel) still override this.
    @State var collabPanel: CollabRightPanel = .kanban
    @State var showCompleteConfirm = false
    @State var showRenameAlert = false
    @State var renameDraft = ""
    @State var standardMode: StandardProjectMode = .edit
    @State var collabDiscussionChannelId: String?
    @State var collabChannelLoadError: String?
    // Cancelable task handles so rapid project/thread switches don't queue
    // up redundant fetches.
    @State var threadLoadTask: Task<Void, Never>?
    @State var refreshTask: Task<Void, Never>?
    @State var ensureChannelTask: Task<Void, Never>?
    @AppStorage("mw-chat-theme") var lightMode = false
    @AppStorage("mw-model") var selectedModelId = "flash"
    @AppStorage("mw-preview-collapsed") var previewCollapsed = false

    @MainActor
    init(projectId: String, isEmbedded: Bool = false) {
        self.projectId = projectId
        self.isEmbedded = isEmbedded
        // Main-window tabs share a cached VM (WorkDetailVMStore) so re-opening a
        // project repaints instantly from retained data. Embedded panes (split /
        // aux window) get a private VM so they never share WS callbacks or clobber
        // the main tab's state.
        _viewModel = State(initialValue: isEmbedded
            ? ProjectDetailViewModel()
            : WorkDetailVMStore.shared.projectVM(projectId))
    }

    /// True for general-shaped projects that use `standardLayout` (sections +
    /// chat). Used to gate the Edit/Preview tab toggle in the toolbar so it
    /// doesn't show on recruiting / blog (which already has its own preview tab) /
    /// collab / discipline.
    var isStandardLayout: Bool {
        let t = viewModel.project?.projectType ?? ""
        return !["recruiting", "blog", "collab", "discipline"].contains(t)
    }

    var selectedModelValue: String? {
        mwModelOptions.first { $0.id == selectedModelId }?.value
    }

    var body: some View {
        Group {
            if viewModel.project == nil {
                // Until the project loads we don't know its type. Show a loader
                // rather than falling through to standardLayout — otherwise a
                // collab project briefly flashes the Sections/Chats layout.
                projectLoadingView
            } else if viewModel.project?.projectType == "recruiting" {
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
            // Re-point at the cached VM for THIS project. On a project→project
            // switch the view is reused (init doesn't re-run), so the @State VM
            // would still be the previous project's — repoint it before loading
            // so we don't load new data into another project's cached VM.
            if !isEmbedded {
                let cached = WorkDetailVMStore.shared.projectVM(projectId)
                if cached !== viewModel { viewModel = cached }
            }
            // Single .task: wire realtime callbacks → connect/join WS →
            // then load the project. Sequencing matters: the previous
            // two-block layout relied on SwiftUI's "best effort" ordering
            // between adjacent .task modifiers, which sometimes raced the
            // first task.updated event into a window where callbacks
            // weren't attached yet. SwiftUI auto-cancels this block when
            // projectId changes.
            viewModel.attachTaskRealtime(currentUserId: appState.currentUser?.id,
                                         projectId: projectId,
                                         showToasts: !isEmbedded)
            // Deep-link from a notification tap: open the requested panel
            // (e.g. kanban for a task notification), then clear the hint.
            if !isEmbedded, let panel = appState.pendingProjectPanel {
                collabPanel = panel
                appState.pendingProjectPanel = nil
            }
            presenceVM.start(projectId: projectId, pageKey: collabPanel.rawValue)
            await viewModel.loadProject(id: projectId)
            // An aux window must not write the shared nav/tab context.
            if !isEmbedded {
                appState.setActiveContext(WorkTab(kind: .project, entityId: projectId,
                                                  title: viewModel.project?.title ?? "Workspace"))
            }
        }
        // Same project already open when the notification fires: projectId
        // doesn't change so the .task above won't re-run — catch it here.
        .onChange(of: appState.pendingProjectPanel) { _, panel in
            if !isEmbedded, let panel {
                collabPanel = panel
                appState.pendingProjectPanel = nil
            }
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
                    Menu {
                        ForEach(mwProjectIconOptions, id: \.self) { sym in
                            Button {
                                Task { await viewModel.setProjectIcon(sym) }
                            } label: {
                                Label(sym, systemImage: sym)
                            }
                        }
                    } label: {
                        Image(systemName: project.icon ?? "square.grid.2x2")
                            .font(.system(size: 13))
                            .foregroundColor(appState.themeAccent)
                    }
                    .menuStyle(.borderlessButton)
                    .fixedSize()
                    .help("Change workspace icon")
                }
            }
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
                                    .foregroundColor(appState.themeText.opacity(0.45))
                                Text("·")
                                    .font(.system(size: 12))
                                    .foregroundColor(appState.themeText.opacity(0.3))
                            }
                            Text(project.title)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(appState.themeText)
                            Image(systemName: "pencil")
                                .font(.system(size: 9))
                                .foregroundColor(appState.themeText.opacity(0.4))
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
                    .background(appState.themeCard)
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
                    .help("Collab workspace guide")
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
                        .help("Mark workspace complete")
                        .confirmationDialog(
                            "Mark workspace complete?",
                            isPresented: $showCompleteConfirm,
                            titleVisibility: .visible
                        ) {
                            Button("Complete") {
                                Task { await viewModel.markProjectComplete() }
                            }
                            Button("Cancel", role: .cancel) {}
                        } message: {
                            Text("Owner only. Workspace will move to the Completed section.")
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
                .help("Export workspace")

                Menu {
                    Button("Archive") {
                        guard let pid = viewModel.project?.id else { return }
                        Task {
                            try? await MatchaWorkService.shared.archiveProject(id: pid)
                            await MainActor.run {
                                if appState.selectedProjectId == pid { appState.selectedProjectId = nil }
                                appState.projectsListGeneration &+= 1
                            }
                        }
                    }
                    Divider()
                    Button("Delete…") {
                        guard let p = viewModel.project else { return }
                        let alert = NSAlert()
                        alert.messageText = "Delete \"\(p.title)\"?"
                        alert.informativeText = "Permanently deletes the workspace, its sections, and all associated threads and messages. Cannot be undone."
                        alert.alertStyle = .critical
                        alert.addButton(withTitle: "Delete Permanently")
                        alert.addButton(withTitle: "Cancel")
                        if alert.runModal() == .alertFirstButtonReturn {
                            Task {
                                try? await MatchaWorkService.shared.deleteProject(id: p.id)
                                await MainActor.run {
                                    appState.closeTab(WorkTab(kind: .project, entityId: p.id, title: p.title))
                                    if appState.selectedProjectId == p.id { appState.selectedProjectId = nil }
                                    appState.projectsListGeneration &+= 1
                                }
                            }
                        }
                    }
                } label: {
                    Image(systemName: "ellipsis.circle").font(.system(size: 13))
                }
                .help("Archive or delete workspace")
            }
        }
        .alert("Rename workspace", isPresented: $showRenameAlert) {
            TextField("Workspace title", text: $renameDraft)
            Button("Save") {
                let trimmed = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmed.isEmpty else { return }
                Task { await viewModel.updateTitle(trimmed) }
            }
            Button("Cancel", role: .cancel) {}
        }
    }
}
