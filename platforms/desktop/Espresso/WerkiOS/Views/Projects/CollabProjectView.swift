import SwiftUI

/// The same compact workspace for solo and collaborative projects. Desktop-only
/// project types deliberately keep their specialist workflows on desktop.
struct CollabProjectView: View {
    enum Panel: String, CaseIterable, Identifiable {
        case tasks = "Tasks", notes = "Notes", files = "Files", chat = "Chat", overview = "Overview"
        var id: String { rawValue }
        var symbol: String {
            switch self {
            case .tasks: return "checklist"
            case .notes: return "doc.text"
            case .files: return "folder"
            case .chat: return "bubble.left.and.bubble.right"
            case .overview: return "chart.pie"
            }
        }
    }
    let projectId: String
    let initialTaskId: String?
    private let isPreview: Bool
    @Environment(AppState.self) private var appState
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var panel: Panel = .tasks
    @State private var vm: ProjectDetailViewModel
    @State private var presence = ProjectPresenceViewModel()
    @State private var selectedTask: MWProjectTask?
    @State private var creatingTask = false
    @State private var showingPeople = false
    @State private var editingProject = false
    @State private var showingAssistant = false
    @State private var taskSearch = ""
    @State private var onlyMine = false
    @State private var initialTaskConsumed = false

    init(projectId: String, initialTaskId: String? = nil, previewVM: ProjectDetailViewModel? = nil) {
        self.projectId = projectId; self.initialTaskId = initialTaskId
        isPreview = previewVM != nil
        _vm = State(initialValue: previewVM ?? WorkDetailVMStore.shared.projectVM(projectId))
    }
    private var isCollab: Bool { vm.project?.projectType == "collab" }
    private var panels: [Panel] { Panel.allCases }

    var body: some View {
        VStack(spacing: 0) {
            if let project = vm.project {
                projectHeader(project)
                panelPicker
                Group {
                    switch panel {
                    case .tasks: taskList
                    case .notes: MobileProjectNotes(vm: vm, projectId: projectId)
                    case .files: MobileProjectFiles(vm: vm, projectId: projectId)
                    case .chat:
                        if isCollab { CollabChatPanel(projectId: projectId, projectName: project.title) }
                        else { MobileProjectAssistant(projectId: projectId) }
                    case .overview: overview
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.isLoading { ProgressView("Opening your workspace…").frame(maxWidth: .infinity, maxHeight: .infinity) }
            else {
                EspressoEmptyState(title: "Couldn't open this project", message: "It may have moved, or your connection may be offline.", symbol: "folder.badge.questionmark")
                Button("Try again") { Task { await refresh() } }
                Spacer()
            }
        }
        .espressoBackground()
        .navigationTitle(vm.project?.title ?? "Project").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button("Refresh", systemImage: "arrow.clockwise") { Task { await refresh() } }
                    Button("Ask Espresso", systemImage: "sparkles") { showingAssistant = true }
                    if isCollab { Button("People", systemImage: "person.2") { showingPeople = true } }
                    if vm.project?.mobileIsOwner == true {
                        Button("Edit project", systemImage: "pencil") { editingProject = true }
                    }
                } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel("Project actions")
            }
        }
        .sheet(item: $selectedTask) { MobileTaskSheet(vm: vm, projectId: projectId, task: $0) }
        .sheet(isPresented: $creatingTask) { MobileTaskSheet(vm: vm, projectId: projectId) }
        .sheet(isPresented: $showingPeople) { MobileProjectPeople(vm: vm, projectId: projectId) }
        .sheet(isPresented: $showingAssistant) {
            NavigationStack { MobileProjectAssistant(projectId: projectId).navigationTitle("Ask Espresso").toolbar { Button("Done") { showingAssistant = false } } }
        }
        .sheet(isPresented: $editingProject) {
            MobileProjectEditor(project: vm.project) { updated in vm.project = updated }
        }
        .espressoError($vm.errorMessage)
        .task {
            guard !isPreview else { return }
            await refresh()
            vm.attachTaskRealtime(currentUserId: appState.currentUser?.id, projectId: projectId, showToasts: false)
            presence.start(projectId: projectId, pageKey: panel.rawValue.lowercased())
            if let initialTaskId, !initialTaskConsumed {
                initialTaskConsumed = true
                if !vm.tasks.contains(where: { $0.id == initialTaskId }) { await vm.loadAllDoneTasks() }
                if let task = vm.tasks.first(where: { $0.id == initialTaskId }) { selectedTask = task }
                else { vm.errorMessage = "This task is no longer available in the mobile task list." }
            }
        }
        .onChange(of: panel) { _, value in presence.setPage(value.rawValue.lowercased()) }
        .onChange(of: scenePhase) { _, phase in if phase == .active && !isPreview { Task { await refresh() } } }
        .onDisappear { if !isPreview { presence.stop(); ProjectWebSocket.shared.unregisterTaskHandlers(owner: vm) } }
    }

    private func projectHeader(_ project: MWProject) -> some View {
        HStack(spacing: 12) {
            EspressoProjectGlyph(symbol: project.icon ?? "folder", color: isCollab ? EspressoStyle.sage : EspressoStyle.accent)
            VStack(alignment: .leading, spacing: 4) {
                if !dynamicTypeSize.isAccessibilitySize {
                    Text(isCollab ? "BETTER, TOGETHER" : "A SPACE OF YOUR OWN").font(.caption2.weight(.semibold)).tracking(1.3).foregroundStyle(.secondary)
                }
                Text(project.title).font(dynamicTypeSize.isAccessibilitySize ? .headline : .title2.weight(.semibold))
                    .tracking(-0.45).lineLimit(2)
            }
            Spacer(minLength: 0)
            if isCollab {
                Button { showingPeople = true } label: { Image(systemName: "person.2").font(.system(size: 18, weight: .medium)).frame(width: 44, height: 44).espressoGlass() }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Project people")
            }
        }.padding(.horizontal, 20).padding(.vertical, 16)
    }

    private var panelPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            EspressoGlassGroup {
                HStack(spacing: 10) {
                    ForEach(panels) { option in
                        Button { panel = option } label: {
                            Label(option == .chat && !isCollab ? "Espresso" : option.rawValue, systemImage: option == .chat && !isCollab ? "sparkles" : option.symbol).font(.subheadline.weight(.semibold))
                                .padding(.horizontal, 16).frame(minHeight: 44)
                                .espressoGlass(selected: panel == option)
                        }.buttonStyle(.plain).accessibilityAddTraits(panel == option ? .isSelected : [])
                    }
                }
            }.padding(.horizontal, 20).padding(.vertical, 8)
        }.scrollClipDisabled()
    }

    private var taskList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                HStack {
                    Label { TextField("Search tasks", text: $taskSearch, prompt: Text("Search tasks").foregroundStyle(EspressoStyle.placeholder)) } icon: { Image(systemName: "magnifyingglass").foregroundStyle(.secondary) }
                        .padding(14).espressoSurface(cornerRadius: 20)
                    Button { creatingTask = true } label: { Image(systemName: "plus").font(.system(size: 20, weight: .medium)).frame(width: 48, height: 48).espressoGlass(selected: true) }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Add task")
                        .disabled(vm.project?.mobileCanEdit != true)
                }
                Toggle("Assigned to me", isOn: $onlyMine).font(.subheadline).tint(EspressoStyle.sage)
                if vm.tasks.isEmpty {
                    EspressoEmptyState(title: "One small step", message: "Add your first task and give this project a little momentum.", symbol: "checkmark.circle")
                }
                let columns = vm.groupedColumns(pipeline: false, search: taskSearch)
                if !vm.tasks.isEmpty && columns.values.flatMap({ $0 }).filter({ !onlyMine || $0.assignedTo == appState.currentUser?.id }).isEmpty {
                    EspressoEmptyState(title: "A clear desk", message: "No tasks match these filters.", symbol: "checkmark.circle")
                }
                ForEach(kanbanColumns, id: \.key) { column in
                    let tasks = columns[column.key, default: []].filter { !onlyMine || $0.assignedTo == appState.currentUser?.id }
                    if !tasks.isEmpty {
                        EspressoSectionHeading(title: column.label, detail: "\(tasks.count)").padding(.top, 12)
                        ForEach(tasks) { task in
                            Button { selectedTask = task } label: { MobileTaskRow(task: task) }.buttonStyle(EspressoPressStyle())
                        }
                    }
                }
                if vm.doneScope != "all" && vm.doneTotal > vm.tasks.filter({ $0.boardColumn == "done" }).count {
                    Button("Load earlier completed tasks", systemImage: "clock.arrow.circlepath") { Task { await vm.loadAllDoneTasks() } }
                        .frame(maxWidth: .infinity).padding()
                } else if vm.doneScope == "all" && vm.doneTotal > vm.tasks.filter({ $0.boardColumn == "done" }).count {
                    Text("Showing the most recent completed tasks. Older history is available on desktop.").font(.caption).foregroundStyle(.secondary)
                }
            }.padding(20).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }.refreshable { await refresh() }
    }

    private var overview: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 16) {
                    EspressoSectionHeading(title: "Moving forward", detail: "This workspace")
                    TaskProgressBar(tasks: vm.tasks)
                    Text("Progress reflects the loaded tasks, including this week's completed work.").font(.caption).foregroundStyle(.secondary)
                }.espressoCard()
                EspressoSectionHeading(title: "Recent activity")
                if vm.recentActivity.isEmpty { Text("Your project's story starts here.").foregroundStyle(.secondary) }
                ForEach(vm.recentActivity) { item in
                    HStack(alignment: .top, spacing: 14) {
                        Image(systemName: item.icon).foregroundStyle(EspressoStyle.accent).frame(width: 24)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(item.text).font(.subheadline)
                            Text(item.timestamp, style: .relative).font(.caption).foregroundStyle(.secondary)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
            }.padding(20).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }.refreshable { await refresh() }
    }

    private func refresh() async { await vm.loadProject(id: projectId); await vm.loadProjectActivity() }
}

struct MobileTaskRow: View {
    let task: MWProjectTask
    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: task.boardColumn == "done" ? "checkmark.circle.fill" : "circle")
                .font(.title3).foregroundStyle(task.boardColumn == "done" ? EspressoStyle.sage : Color.secondary)
            VStack(alignment: .leading, spacing: 12) {
                Text(task.title).font(.headline).multilineTextAlignment(.leading).foregroundStyle(.primary)
                ViewThatFits(in: .horizontal) {
                    HStack { metadata }
                    VStack(alignment: .leading, spacing: 8) { metadata }
                }
            }
            Spacer(minLength: 0)
        }.espressoCard()
    }
    @ViewBuilder private var metadata: some View {
        EspressoBadge(text: task.priority.capitalized, color: EspressoStyle.priority(task.priority))
        if let name = task.displayAssignee { Text(name).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
        if let due = MobileTaskDates.parse(task.dueDate) { Label(due.formatted(date: .abbreviated, time: .omitted), systemImage: "calendar").font(.caption).foregroundStyle(.secondary) }
        if let total = task.subtaskTotal, total > 0 { Label("\(task.subtaskDone ?? 0)/\(total)", systemImage: "checklist").font(.caption).foregroundStyle(.secondary) }
    }
}

struct CollabChatPanel: View {
    let projectId: String
    let projectName: String
    @State private var channelId: String?
    @State private var errorMessage: String?
    var body: some View {
        Group {
            if let channelId { ChannelChatView(channelId: channelId, channelName: projectName, isEmbedded: true) }
            else if let errorMessage {
                VStack {
                    EspressoEmptyState(title: "Couldn't open chat", message: errorMessage, symbol: "bubble.left")
                    Button("Retry") { Task { await loadChannel() } }
                }
            } else { ProgressView() }
        }.task { if channelId == nil { await loadChannel() } }
    }
    private func loadChannel() async {
        errorMessage = nil
        do { channelId = try await MatchaWorkService.shared.ensureProjectDiscussionChannel(projectId: projectId) }
        catch { errorMessage = error.localizedDescription }
    }
}
