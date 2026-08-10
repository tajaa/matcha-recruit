import SwiftUI

struct ProjectsListView: View {
    private struct Destination: Hashable {
        let projectId: String
        let taskId: String?
    }

    @Environment(AppState.self) private var appState
    @State private var vm = ProjectsListViewModel()
    @State private var path: [Destination] = []

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if vm.isLoading { ProgressView() }
                else if vm.projects.isEmpty { ContentUnavailableView("No projects", systemImage: "square.grid.2x2", description: Text(vm.errorMessage ?? "Your collab projects will appear here.")) }
                else { List(vm.projects) { project in
                    NavigationLink(value: Destination(projectId: project.id, taskId: nil)) {
                        HStack { Image(systemName: project.icon ?? "square.grid.2x2"); VStack(alignment: .leading) { Text(project.title).fontWeight(.semibold); Text(project.status ?? "Active").font(.caption).foregroundStyle(.secondary) } }
                    }
                }.refreshable { await vm.load() } }
            }
            .navigationTitle("Projects")
            .navigationDestination(for: Destination.self) { destination in
                CollabProjectView(projectId: destination.projectId, initialTaskId: destination.taskId)
            }
        }
        .task {
            await vm.load()
            consumePendingProject()
        }
        .onChange(of: appState.pendingProjectId) { _, _ in consumePendingProject() }
    }

    private func consumePendingProject() {
        guard let projectId = appState.pendingProjectId else { return }
        let taskId = appState.pendingTaskId
        path = [Destination(projectId: projectId, taskId: taskId)]
        appState.pendingProjectId = nil
        appState.pendingTaskId = nil
    }
}
