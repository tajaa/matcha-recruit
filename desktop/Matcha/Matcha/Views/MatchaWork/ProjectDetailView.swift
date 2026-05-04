import SwiftUI
import AppKit
import UniformTypeIdentifiers

enum CollabRightPanel: String, CaseIterable, Identifiable {
    case chat, kanban, files, sections, overview
    var id: String { rawValue }
    var label: String {
        switch self {
        case .chat: return "Chat"
        case .kanban: return "Kanban"
        case .files: return "Files"
        case .sections: return "Sections"
        case .overview: return "Overview"
        }
    }
    var icon: String {
        switch self {
        case .chat: return "bubble.left.and.bubble.right"
        case .kanban: return "rectangle.split.3x1"
        case .files: return "doc.on.doc"
        case .sections: return "list.bullet.rectangle"
        case .overview: return "rectangle.grid.2x2"
        }
    }
    /// Cmd-N shortcut character; index in `allCases` + 1.
    var shortcutKey: KeyEquivalent {
        switch self {
        case .chat: return "1"
        case .kanban: return "2"
        case .files: return "3"
        case .sections: return "4"
        case .overview: return "5"
        }
    }
}

enum StandardProjectMode: String, CaseIterable, Identifiable {
    case edit, preview
    var id: String { rawValue }
    var label: String {
        switch self {
        case .edit: return "Edit"
        case .preview: return "Preview"
        }
    }
}

struct ProjectDetailView: View {
    let projectId: String
    @Environment(AppState.self) private var appState
    @State private var viewModel = ProjectDetailViewModel()
    @State private var chatVM = ThreadDetailViewModel()
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
            // Don't fetch the thread inline here — onChange(activeChatId) below
            // is the single source of truth and fires on initial nil→value.
            // SwiftUI auto-cancels this .task block when projectId changes.
            await viewModel.loadProject(id: projectId)
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
        VStack(spacing: 0) {
            if let sections = viewModel.project?.sections, !sections.isEmpty {
                if let sid = editingSectionId,
                   let section = sections.first(where: { $0.id == sid }) {
                    SectionEditorView(
                        section: section,
                        onSave: { title, content in
                            Task { await viewModel.updateSection(sectionId: sid, title: title, content: content) }
                        }
                    )
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(sections) { section in
                                Button { editingSectionId = section.id } label: {
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

    private var collabOverview: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let project = viewModel.project {
                    overviewHeader(project: project)
                    HStack(alignment: .top, spacing: 14) {
                        upNextCard.frame(maxWidth: .infinity, alignment: .topLeading)
                        recentActivityCard.frame(maxWidth: .infinity, alignment: .topLeading)
                    }
                    peopleCard(project: project)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
        }
    }

    private func overviewHeader(project: MWProject) -> some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(project.title)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)
                HStack(spacing: 10) {
                    headerChip(icon: "list.bullet", label: "\(viewModel.tasks.count) tasks")
                    headerChip(icon: "doc", label: "\(viewModel.files.count) files")
                    headerChip(icon: "person.2", label: "\(project.collaborators?.count ?? 0) collaborators")
                }
            }
            Spacer()
            Menu {
                Button("PDF") { export(format: "pdf") }
                Button("Markdown") { export(format: "md") }
                Button("DOCX") { export(format: "docx") }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "square.and.arrow.up").font(.system(size: 11))
                    Text("Export").font(.system(size: 11, weight: .medium))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.matcha600)
                .cornerRadius(5)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Export the project as PDF, Markdown, or DOCX")
        }
    }

    private func headerChip(icon: String, label: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9))
            Text(label).font(.system(size: 10))
        }
        .foregroundColor(.white.opacity(0.55))
    }

    private var upNextCard: some View {
        let upcoming = upcomingTasks()
        return VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "UP NEXT", trailing: upcoming.isEmpty ? nil : "\(upcoming.count)")
            if upcoming.isEmpty {
                Text("No open tasks. Add one in Kanban.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(upcoming) { task in
                    Button {
                        collabPanel = .kanban
                    } label: {
                        HStack(spacing: 8) {
                            Circle().fill(priorityColor(task.priority)).frame(width: 6, height: 6)
                            Text(task.title)
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.85))
                                .lineLimit(1)
                            Spacer()
                            if let due = task.dueDate, !due.isEmpty {
                                Text(due.prefix(10))
                                    .font(.system(size: 9))
                                    .foregroundColor(.white.opacity(0.4))
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private var recentActivityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "RECENT ACTIVITY", trailing: nil)
            if viewModel.recentActivity.isEmpty {
                Text("No activity yet this session.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(viewModel.recentActivity.prefix(5)) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: item.icon)
                            .font(.system(size: 10))
                            .foregroundColor(.matcha500)
                            .frame(width: 12)
                        Text(item.text)
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.75))
                            .lineLimit(2)
                        Spacer()
                        Text(relativeTime(from: item.timestamp))
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.4))
                    }
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private func peopleCard(project: MWProject) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                cardHeader(title: "PEOPLE", trailing: "\(project.collaborators?.count ?? 0)")
                Spacer()
                Button { showCollaborators = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "person.badge.plus").font(.system(size: 10))
                        Text("Invite").font(.system(size: 11, weight: .medium))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(Color.matcha600)
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
                .help("Invite a collaborator")
            }
            if let collabs = project.collaborators, !collabs.isEmpty {
                ForEach(collabs) { c in
                    HStack(spacing: 8) {
                        Circle().fill(Color.matcha500).frame(width: 22, height: 22)
                            .overlay(Text(String(c.name.prefix(1)).uppercased())
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(.white))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(c.name).font(.system(size: 12)).foregroundColor(.white)
                            Text(c.email).font(.system(size: 10)).foregroundColor(.secondary)
                        }
                        Spacer()
                        if c.role == "owner" {
                            Text("Owner")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.matcha500)
                        }
                    }
                    .padding(.vertical, 2)
                }
            } else {
                Text("No collaborators yet — click Invite to add someone.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private func cardHeader(title: String, trailing: String?) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            if let trailing {
                Text(trailing)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.zinc800.opacity(0.7))
                    .cornerRadius(3)
            }
            Spacer()
        }
    }

    private func priorityColor(_ priority: String) -> Color {
        switch priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .white.opacity(0.4)
        }
    }

    /// Top 5 open tasks sorted by priority bucket then due date.
    private func upcomingTasks() -> [MWProjectTask] {
        let priorityRank: (String) -> Int = { p in
            switch p {
            case "critical": return 0
            case "high": return 1
            case "medium": return 2
            case "low": return 3
            default: return 4
            }
        }
        return viewModel.tasks
            .filter { $0.status != "completed" }
            .sorted { a, b in
                let ar = priorityRank(a.priority), br = priorityRank(b.priority)
                if ar != br { return ar < br }
                return (a.dueDate ?? "9999-99-99") < (b.dueDate ?? "9999-99-99")
            }
            .prefix(5)
            .map { $0 }
    }

    private func relativeTime(from date: Date) -> String {
        let secs = Int(Date().timeIntervalSince(date))
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(secs/60)m" }
        if secs < 86400 { return "\(secs/3600)h" }
        return "\(secs/86400)d"
    }

    private func statChip(icon: String, label: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon).font(.system(size: 10))
            Text(label).font(.system(size: 11))
        }
        .foregroundColor(.secondary)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.zinc800)
        .cornerRadius(6)
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
