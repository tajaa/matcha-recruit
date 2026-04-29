import SwiftUI
import AppKit
import UniformTypeIdentifiers

enum CollabRightPanel: String, CaseIterable, Identifiable {
    case kanban, files, sections, overview
    var id: String { rawValue }
    var label: String {
        switch self {
        case .kanban: return "Kanban"
        case .files: return "Files"
        case .sections: return "Sections"
        case .overview: return "Overview"
        }
    }
}

struct ProjectDetailView: View {
    let projectId: String
    @State private var viewModel = ProjectDetailViewModel()
    @State private var chatVM = ThreadDetailViewModel()
    @State private var editingSectionId: String?
    @State private var newSectionTitle = ""
    @State private var showCollaborators = false
    @State private var showExportMenu = false
    @State private var collabPanel: CollabRightPanel = .kanban
    @State private var showCompleteConfirm = false
    @AppStorage("mw-chat-theme") private var lightMode = false
    @AppStorage("mw-model") private var selectedModelId = "flash"

    private var selectedModelValue: String? {
        mwModelOptions.first { $0.id == selectedModelId }?.value
    }

    var body: some View {
        Group {
            if viewModel.project?.projectType == "recruiting" {
                recruitingLayout
            } else if viewModel.project?.projectType == "consultation" {
                consultationLayout
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
            await viewModel.loadProject(id: projectId)
            if let chatId = viewModel.activeChatId {
                await chatVM.loadThread(id: chatId)
            }
        }
        .onChange(of: viewModel.activeChatId) {
            if let chatId = viewModel.activeChatId {
                Task { await chatVM.loadThread(id: chatId) }
            }
        }
        // Chat streams mutate project data (sections for blog, posting for
        // recruiting, consultation fields, etc.) via server-side directives.
        // Refetch the project when a stream completes so the panel reflects
        // the new state without requiring the user to navigate away and back.
        .onReceive(NotificationCenter.default.publisher(for: .mwProjectDataChanged)) { _ in
            Task { await viewModel.refreshProject() }
        }
        .toolbar {
            ToolbarItem(placement: .navigation) {
                if let project = viewModel.project {
                    Text(project.title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            ToolbarItemGroup(placement: .primaryAction) {
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
    }

    private var collabLayout: some View {
        HSplitView {
            if viewModel.activeChatId != nil {
                ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModelValue)
                    .frame(minWidth: 340)
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
                        ProgressView().tint(.secondary)
                        Text("Starting chat…")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }
                .frame(minWidth: 340)
                .background(Color.appBackground)
                .task {
                    if viewModel.activeChatId == nil && viewModel.errorMessage == nil {
                        await viewModel.createChat(title: nil)
                    }
                }
            }

            VStack(spacing: 0) {
                Picker("", selection: $collabPanel) {
                    ForEach(CollabRightPanel.allCases) { p in
                        Text(p.label).tag(p)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)

                Divider().opacity(0.3)

                switch collabPanel {
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
            .frame(minWidth: 440)
            .background(Color.appBackground)
        }
        .background(Color.appBackground)
    }

    private var collabSections: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Sections")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.secondary)
                Spacer()
                Button { Task { await viewModel.addSection(title: "New Section") } } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Add section")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider().opacity(0.3)

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
        VStack(alignment: .leading, spacing: 12) {
            if let project = viewModel.project {
                Text(project.title)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)

                HStack(spacing: 14) {
                    statChip(icon: "list.bullet", label: "\(viewModel.tasks.count) tasks")
                    statChip(icon: "doc", label: "\(viewModel.files.count) files")
                    statChip(icon: "person.2", label: "\(project.collaborators?.count ?? 0) collaborators")
                }

                Divider().opacity(0.3).padding(.top, 6)

                HStack {
                    Text("COLLABORATORS")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.secondary)
                        .tracking(0.5)
                    Spacer()
                    Button { showCollaborators = true } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "person.badge.plus").font(.system(size: 10))
                            Text("Invite").font(.system(size: 11, weight: .medium))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.matcha600)
                        .cornerRadius(5)
                    }
                    .buttonStyle(.plain)
                    .help("Invite a collaborator to this project")
                }

                if let collabs = project.collaborators, !collabs.isEmpty {
                    ForEach(collabs) { c in
                        HStack(spacing: 8) {
                            Circle().fill(Color.matcha500).frame(width: 22, height: 22)
                                .overlay(Text(String(c.name.prefix(1)).uppercased()).font(.system(size: 9, weight: .bold)).foregroundColor(.white))
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
                    }
                } else {
                    Text("No collaborators yet — click Invite to add someone.")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .padding(.vertical, 4)
                }
                Spacer()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
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

    private var consultationLayout: some View {
        HSplitView {
            if viewModel.activeChatId != nil {
                ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModelValue)
                    .frame(minWidth: 320)
            } else {
                VStack(spacing: 12) {
                    Spacer()
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("Starting chat…")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
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

            ConsultationDetailView(viewModel: viewModel)
                .frame(minWidth: 340)
        }
        .background(Color.appBackground)
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

    private var standardLayout: some View {
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
        Task { @MainActor in
            guard let data = await viewModel.exportProject(format: format) else {
                // exportProject sets viewModel.errorMessage on failure; surface
                // it as an alert so the user sees why nothing happened instead
                // of a silent no-op.
                if let msg = viewModel.errorMessage {
                    let alert = NSAlert()
                    alert.messageText = "Export failed"
                    alert.informativeText = msg
                    alert.alertStyle = .warning
                    alert.runModal()
                }
                return
            }
            let panel = NSSavePanel()
            panel.nameFieldStringValue = "\(viewModel.project?.title ?? "project").\(format)"
            // allowedContentTypes pins the save dialog to the correct extension
            // and makes sure the file is written with it even if the user edits
            // the name field without the extension.
            switch format {
            case "pdf": panel.allowedContentTypes = [.pdf]
            case "docx":
                if let t = UTType(filenameExtension: "docx") { panel.allowedContentTypes = [t] }
            case "md":
                if let t = UTType(filenameExtension: "md") { panel.allowedContentTypes = [t] }
            default: break
            }
            let window = NSApp.keyWindow ?? NSApp.mainWindow
            let handler: (NSApplication.ModalResponse) -> Void = { response in
                guard response == .OK, let url = panel.url else { return }
                do {
                    try data.write(to: url)
                } catch {
                    print("[Export] write failed: \(error)")
                }
            }
            if let window {
                panel.beginSheetModal(for: window, completionHandler: handler)
            } else {
                panel.begin(completionHandler: handler)
            }
        }
    }
}
