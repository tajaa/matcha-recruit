import SwiftUI

struct CollabProjectView: View {
    enum Panel: String, CaseIterable, Identifiable { case overview = "Overview", chat = "Chat", kanban = "Kanban", files = "Files", media = "Media", notes = "Notes"; var id: String { rawValue } }
    let projectId: String
    let initialTaskId: String?
    @Environment(AppState.self) private var appState
    @State private var panel: Panel = .overview
    @State private var vm: ProjectDetailViewModel
    @State private var presence = ProjectPresenceViewModel()
    @State private var selectedTaskId: String?

    init(projectId: String, initialTaskId: String? = nil) {
        self.projectId = projectId
        self.initialTaskId = initialTaskId
        _vm = State(initialValue: WorkDetailVMStore.shared.projectVM(projectId))
    }
    var body: some View {
        VStack(spacing: 0) {
            if !presence.members.isEmpty {
                HStack { Spacer(); PresencePillContent(members: presence.members) }
                    .padding(.horizontal).padding(.top, 4)
            }
            Picker("Panel", selection: $panel) { ForEach(Panel.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented).padding()
            Group {
                switch panel {
                case .overview: overview
                case .chat: CollabChatPanel(projectId: projectId, projectName: vm.project?.title ?? "Project")
                case .kanban: kanban
                case .files: fileList(files: vm.files.filter { !$0.isImage }, empty: "No files yet.")
                case .media: fileList(files: vm.files.filter(\.isImage), empty: "No media yet.")
                case .notes: ScrollView { VStack(alignment: .leading, spacing: 16) { ForEach(vm.project?.sections ?? []) { section in VStack(alignment: .leading, spacing: 6) { Text(section.title).font(.headline); Text(section.content ?? "").foregroundStyle(.secondary) } } }.frame(maxWidth: .infinity, alignment: .leading).padding() }
                }
            }
        }
        .navigationTitle(vm.project?.title ?? "Project")
        .task {
            await vm.loadProject(id: projectId)
            vm.attachTaskRealtime(currentUserId: appState.currentUser?.id, projectId: projectId, showToasts: false)
            await vm.loadProjectActivity()
            presence.start(projectId: projectId, pageKey: panel.rawValue.lowercased())
            if let initialTaskId, vm.tasks.contains(where: { $0.id == initialTaskId }) {
                panel = .kanban
                selectedTaskId = initialTaskId
            }
        }
        .onChange(of: panel) { _, value in presence.setPage(value.rawValue.lowercased()) }
        .onDisappear {
            presence.stop()
            ProjectWebSocket.shared.unregisterTaskHandlers(owner: vm)
        }
        .sheet(isPresented: Binding(get: { selectedTaskId != nil }, set: { if !$0 { selectedTaskId = nil } })) {
            if let selectedTaskId {
                CollabTicketSheet(vm: vm, taskId: selectedTaskId)
            }
        }
    }
    private var overview: some View { List { Section("Progress") { TaskProgressBar(tasks: vm.tasks) }; Section("Collaborators") { ForEach(vm.collaborators) { Text($0.name) } }; Section("Recent activity") { ForEach(vm.recentActivity) { Text($0.text) } } } }

    private var kanban: some View {
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 12) {
                let columns = vm.groupedColumns(pipeline: false, search: "")
                ForEach(kanbanColumns, id: \.key) { column in
                    VStack(alignment: .leading, spacing: 8) {
                        Text("\(column.label) (\(columns[column.key, default: []].count))").font(.headline)
                        ForEach(columns[column.key, default: []]) { task in
                            Button { selectedTaskId = task.id } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(task.title).font(.subheadline.weight(.semibold)).multilineTextAlignment(.leading)
                                    Text(task.priority.capitalized).font(.caption).foregroundStyle(.secondary)
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(10).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                            }.buttonStyle(.plain)
                        }
                    }.frame(width: 230, alignment: .leading)
                }
            }.padding()
        }
    }

    @ViewBuilder private func fileList(files: [MWProjectFile], empty: String) -> some View {
        if files.isEmpty { ContentUnavailableView(empty, systemImage: "folder") }
        else { List(files) { file in
            if SafeURL.isAllowed(file.storageUrl), let url = URL(string: file.storageUrl) {
                Link(file.filename, destination: url)
            } else { Text(file.filename).foregroundStyle(.secondary) }
        } }
    }
}

struct CollabChatPanel: View {
    let projectId: String
    let projectName: String
    @State private var channelId: String?
    @State private var errorMessage: String?
    var body: some View { Group { if let channelId { ChannelChatView(channelId: channelId, channelName: projectName, isEmbedded: true) } else if let errorMessage { ContentUnavailableView("Couldn't open chat", systemImage: "exclamationmark.triangle", description: Text(errorMessage)).overlay(alignment: .bottom) { Button("Retry") { Task { await loadChannel() } }.padding() } } else { ProgressView() } }.task { await loadChannel() } }
    private func loadChannel() async { do { channelId = try await MatchaWorkService.shared.ensureProjectDiscussionChannel(projectId: projectId); errorMessage = nil } catch { errorMessage = error.localizedDescription } }
}

private struct CollabTicketSheet: View {
    @Environment(\.dismiss) private var dismiss
    let vm: ProjectDetailViewModel
    let taskId: String

    private var task: MWProjectTask? { vm.tasks.first { $0.id == taskId } }

    var body: some View {
        NavigationStack {
            Group {
                if let task { ticketContent(task) }
                else { ContentUnavailableView("Ticket unavailable", systemImage: "exclamationmark.triangle") }
            }.navigationTitle(task?.title ?? "Ticket").toolbar { Button("Done") { dismiss() } }
        }
    }

    private func ticketContent(_ task: MWProjectTask) -> some View {
        List {
            ticketDetails(task)
            ticketSubtasks(task)
        }
        .task(id: task.id) { await vm.loadSubtasks(taskId: task.id) }
    }

    private func ticketDetails(_ task: MWProjectTask) -> some View {
        Section("Details") {
            Text(task.description ?? "No description.")
            LabeledContent("Priority", value: task.priority.capitalized)
            Picker("Column", selection: columnBinding(for: task)) {
                ForEach(kanbanColumns, id: \.key) { Text($0.label).tag($0.key) }
            }
        }
    }

    private func ticketSubtasks(_ task: MWProjectTask) -> some View {
        Section("Subtasks") {
            ForEach(vm.taskSubtasks[task.id] ?? []) { subtask in
                Toggle(subtask.title, isOn: subtaskBinding(taskId: task.id, subtask: subtask))
            }
        }
    }

    private func columnBinding(for task: MWProjectTask) -> Binding<String> {
        Binding(get: { task.boardColumn }, set: { value in
            Task { await vm.moveTask(id: task.id, toColumn: value) }
        })
    }

    private func subtaskBinding(taskId: String, subtask: MWSubtask) -> Binding<Bool> {
        Binding(get: { subtask.isDone }, set: { isDone in
            Task { await vm.toggleSubtask(taskId: taskId, subtaskId: subtask.id, isDone: isDone) }
        })
    }
}
