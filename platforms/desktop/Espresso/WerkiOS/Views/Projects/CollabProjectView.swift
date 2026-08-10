import SwiftUI

struct CollabProjectView: View {
    enum Panel: String, CaseIterable, Identifiable { case overview = "Overview", chat = "Chat", kanban = "Kanban", files = "Files", media = "Media", notes = "Notes"; var id: String { rawValue } }
    let projectId: String
    @State private var panel: Panel = .overview
    @State private var vm: ProjectDetailViewModel
    @State private var presence = ProjectPresenceViewModel()

    init(projectId: String) { self.projectId = projectId; _vm = State(initialValue: WorkDetailVMStore.shared.projectVM(projectId)) }
    var body: some View {
        VStack(spacing: 0) {
            Picker("Panel", selection: $panel) { ForEach(Panel.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented).padding()
            Group {
                switch panel {
                case .overview: overview
                case .chat: CollabChatPanel(projectId: projectId, projectName: vm.project?.title ?? "Project")
                case .kanban: List(vm.tasks) { task in VStack(alignment: .leading) { Text(task.title); Text(task.boardColumn.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption).foregroundStyle(.secondary) } }
                case .files, .media: List(vm.files) { file in Link(file.filename, destination: URL(string: file.storageUrl)!) }
                case .notes: ScrollView { Text(vm.project?.sections?.map { $0.title }.joined(separator: "\n\n") ?? "No notes yet.").frame(maxWidth: .infinity, alignment: .leading).padding() }
                }
            }
        }
        .navigationTitle(vm.project?.title ?? "Project")
        .task { await vm.loadProject(id: projectId); presence.start(projectId: projectId, pageKey: panel.rawValue.lowercased()) }
        .onChange(of: panel) { _, value in presence.setPage(value.rawValue.lowercased()) }
        .onDisappear { presence.stop() }
    }
    private var overview: some View { List { Section("Progress") { TaskProgressBar(tasks: vm.tasks) }; Section("Collaborators") { ForEach(vm.collaborators) { Text($0.name) } }; Section("Recent activity") { ForEach(vm.recentActivity) { Text($0.text) } } }.task { await vm.loadProjectActivity() } }
}

struct CollabChatPanel: View {
    let projectId: String
    let projectName: String
    @State private var channelId: String?
    var body: some View { Group { if let channelId { ChannelChatView(channelId: channelId, channelName: projectName, isEmbedded: true) } else { ProgressView() } }.task { channelId = try? await MatchaWorkService.shared.ensureProjectDiscussionChannel(projectId: projectId) } }
}
